"""Minimal Stable-Diffusion (ONNX) pipeline for ROX-Compute.

Supports the ONNX-Runtime demo layout used by onnxruntime/sd-turbo and
onnxruntime/sdxl-turbo:

    text_encoder/model.onnx          (CLIP)
    text_encoder_2/model.onnx        (SDXL only)
    unet/model.onnx                  (denoiser)
    vae_decoder/model.onnx
    tokenizer/(vocab.json,merges.txt)   tokenizer_2/ for SDXL
    scheduler/scheduler_config.json
    model_index.json

Design choices that matter on an 8 GB Polaris card:
  * text encoders run on CPU (used once per prompt) — frees VRAM for UNet
  * UNet + VAE run on the accelerator (DirectML)
  * Turbo models use guidance_scale = 0 (single UNet pass, no CFG)
  * VAE decode is tiled for large outputs
"""
from __future__ import annotations

import functools
import json
import os

import numpy as np


# --------------------------------------------------------------- tokenizer
@functools.lru_cache()
def _bytes_to_unicode():
    bs = (list(range(ord("!"), ord("~") + 1))
          + list(range(ord("\u00a1"), ord("\u00ac") + 1))
          + list(range(ord("\u00ae"), ord("\u00ff") + 1)))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return dict(zip(bs, [chr(c) for c in cs]))


_PAT = r"<\|startoftext\|>|<\|endoftext\|>|'s|'t|'re|'ve|'m|'ll|'d|[a-zA-Z]+|[0-9]|[^\s a-zA-Z0-9]+"


class ClipTokenizer:
    def __init__(self, vocab_path, merges_path):
        self.encoder = json.load(open(vocab_path, encoding="utf-8"))
        merges = open(merges_path, encoding="utf-8").read().split("\n")
        merges = [tuple(m.split()) for m in merges[1:] if len(m.split()) == 2]
        self.ranks = dict(zip(merges, range(len(merges))))
        self.be = _bytes_to_unicode()
        self.cache = {}
        import re
        self.pat = re.compile(_PAT)
        # CLIP pads with its pad_token (often "!" -> id 0), NOT with eos.
        # Getting this wrong shifts every padded position and wrecks the
        # conditioning (the image comes out as abstract noise).
        self.pad_id = 0
        try:
            cfgp = os.path.join(os.path.dirname(vocab_path),
                                "tokenizer_config.json")
            if os.path.exists(cfgp):
                cfg = json.load(open(cfgp, encoding="utf-8"))
                pt = cfg.get("pad_token")
                if isinstance(pt, dict):
                    pt = pt.get("content")
                if isinstance(pt, str) and pt in self.encoder:
                    self.pad_id = self.encoder[pt]
                elif isinstance(pt, int):
                    self.pad_id = pt
        except Exception:
            pass

    def _bpe(self, token):
        if token in self.cache:
            return self.cache[token]
        word = tuple(token[:-1]) + (token[-1] + "</w>",)
        pairs = set(zip(word, word[1:]))
        if not pairs:
            return token + "</w>"
        while True:
            bigram = min(pairs, key=lambda p: self.ranks.get(p, 1e9))
            if bigram not in self.ranks:
                break
            a, b = bigram
            new = []
            i = 0
            while i < len(word):
                if i < len(word) - 1 and word[i] == a and word[i + 1] == b:
                    new.append(a + b)
                    i += 2
                else:
                    new.append(word[i])
                    i += 1
            word = tuple(new)
            if len(word) == 1:
                break
            pairs = set(zip(word, word[1:]))
        out = " ".join(word)
        self.cache[token] = out
        return out

    def encode(self, text, n=77):
        ids = []
        for tok in self.pat.findall(text.lower()):
            tok = "".join(self.be[b] for b in tok.encode("utf-8"))
            for t in self._bpe(tok).split(" "):
                ids.append(self.encoder[t])
        bos = self.encoder["<|startoftext|>"]
        eos = self.encoder["<|endoftext|>"]
        ids = [bos] + ids + [eos]
        ids = ids[:n]
        return ids + [self.pad_id] * (n - len(ids))


# --------------------------------------------------------------- scheduler
class EulerScheduler:
    """Euler / Euler-ancestral matching diffusers' timestep spacing."""

    def __init__(self, cfg, steps=4):
        self.cfg = cfg
        self.set_steps(steps)

    def set_steps(self, steps):
        n = int(self.cfg.get("num_train_timesteps", 1000))
        b0 = float(self.cfg.get("beta_start", 0.00085))
        b1 = float(self.cfg.get("beta_end", 0.012))
        betas = np.linspace(b0 ** 0.5, b1 ** 0.5, n, dtype=np.float64) ** 2
        ac = np.cumprod(1.0 - betas)
        sig_all = np.sqrt((1.0 - ac) / ac)
        spacing = self.cfg.get("timestep_spacing", "trailing")
        off = int(self.cfg.get("steps_offset", 0))
        if spacing == "linspace":
            ts = np.linspace(0, n - 1, steps, dtype=np.float64)[::-1].copy()
        elif spacing == "leading":
            sr = n // steps
            ts = (np.arange(0, steps) * sr).round()[::-1].copy() + off
        else:                                    # trailing (SD-Turbo default)
            sr = n / steps
            ts = np.round(np.arange(n, 0, -sr)).astype(np.float64) - 1
            ts = ts[:steps]
        self.timesteps = ts.astype(np.float32)
        sig = np.interp(ts, np.arange(n), sig_all)
        self.sigmas = np.concatenate([sig, [0.0]])
        self.ancestral = "ancestral" in str(
            self.cfg.get("class_name", "")).lower()

    def init_sigma(self):
        # diffusers: linspace/trailing use sigmas.max(); others sqrt(max^2+1)
        if self.cfg.get("timestep_spacing", "trailing") in ("linspace",
                                                            "trailing"):
            return float(self.sigmas.max())
        return float((self.sigmas.max() ** 2 + 1.0) ** 0.5)

    def scale(self, lat):
        return (lat * self.init_sigma()).astype(np.float32)

    def scale_model_input(self, lat, i):
        """Euler needs the UNet input divided by sqrt(sigma^2 + 1)."""
        s = self.sigmas[i]
        return (lat / np.sqrt(s ** 2 + 1.0)).astype(np.float32)

    def step(self, eps, lat, i, rng):
        s0, s1 = self.sigmas[i], self.sigmas[i + 1]
        if self.ancestral:
            up = np.sqrt(np.maximum(s1 ** 2 * (s0 ** 2 - s1 ** 2) /
                                    (s0 ** 2 + 1e-12), 0.0))
            down = np.sqrt(np.maximum(s1 ** 2 - up ** 2, 0.0))
            # diffusers: dt = sigma_down - sigma  (sigmas decrease)
            prev = lat + eps * (down - s0)
            noise = rng.standard_normal(lat.shape).astype(np.float32)
            return (prev + noise * up).astype(np.float32)
        # diffusers Euler: prev = sample + model_output * (sigma_next - sigma)
        return (lat + eps * (s1 - s0)).astype(np.float32)


# --------------------------------------------------------------- pipeline
def _feather(h, w, overlap):
    """Cosine feather window for blending overlapping tiles."""
    wy = np.ones(h, np.float32)
    wx = np.ones(w, np.float32)
    if overlap > 0:
        r = min(int(overlap), h // 2)
        if r > 0:
            ramp = np.sin(np.linspace(0, np.pi / 2, r,
                                      dtype=np.float32)) ** 2
            wy[:r] = ramp
            wy[-r:] = ramp[::-1]
        r = min(int(overlap), w // 2)
        if r > 0:
            ramp = np.sin(np.linspace(0, np.pi / 2, r,
                                      dtype=np.float32)) ** 2
            wx[:r] = ramp
            wx[-r:] = ramp[::-1]
    return np.outer(wy, wx)


class SD:
    def __init__(self, model_dir, accel="DmlExecutionProvider"):
        import onnxruntime as ort
        self.ort = ort
        self.dir = model_dir
        self.accel = accel if accel in ort.get_available_providers() \
            else "CPUExecutionProvider"
        mi = os.path.join(model_dir, "model_index.json")
        self.meta = json.load(open(mi)) if os.path.exists(mi) else {}
        self.is_xl = os.path.isdir(os.path.join(model_dir, "text_encoder_2"))
        self.sess = {}
        self._load()

    def _mk(self, path, provider):
        so = self.ort.SessionOptions()
        so.graph_optimization_level = \
            self.ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        so.enable_mem_pattern = False
        return self.ort.InferenceSession(path, so, providers=[provider])

    def _load(self):
        d = self.dir
        self.te_path = os.path.join(d, "text_encoder", "model.onnx")
        self.tok = ClipTokenizer(os.path.join(d, "tokenizer", "vocab.json"),
                                 os.path.join(d, "tokenizer", "merges.txt"))
        if self.is_xl:
            self.te2_path = os.path.join(d, "text_encoder_2", "model.onnx")
            self.tok2 = ClipTokenizer(
                os.path.join(d, "tokenizer_2", "vocab.json"),
                os.path.join(d, "tokenizer_2", "merges.txt"))
        self.unet_path = os.path.join(d, "unet", "model.onnx")
        self.vae_path = os.path.join(d, "vae_decoder", "model.onnx")
        self.vae_enc_path = os.path.join(d, "vae_encoder", "model.onnx")
        sc = os.path.join(d, "scheduler", "scheduler_config.json")
        self.sched_cfg = json.load(open(sc)) if os.path.exists(sc) else {}
        # Our sampler is Euler. If the checkpoint ships a different scheduler
        # (PNDM/DDIM/DEIS/...), substitute an Euler config that keeps the
        # same beta schedule and timestep spacing. Euler is a safe, high
        # quality choice for SD1.5-family checkpoints.
        if "euler" not in str(self.sched_cfg.get("_class_name", "")).lower():
            self.sched_cfg = {
                "_class_name": "EulerDiscreteScheduler",
                "beta_start": self.sched_cfg.get("beta_start", 0.00085),
                "beta_end": self.sched_cfg.get("beta_end", 0.012),
                "beta_schedule": self.sched_cfg.get("beta_schedule",
                                                    "scaled_linear"),
                "num_train_timesteps": self.sched_cfg.get(
                    "num_train_timesteps", 1000),
                "timestep_spacing": self.sched_cfg.get("timestep_spacing",
                                                       "leading"),
                "steps_offset": self.sched_cfg.get("steps_offset", 1),
                "prediction_type": self.sched_cfg.get("prediction_type",
                                                      "epsilon"),
                "interpolation_type": "linear",
            }
        self.scale = 0.13025 if self.is_xl else 0.18215

    def _te_session(self, path):
        """Text encoders use MS contrib ops (DML-only kernels), so they run
        on the accelerator — created on demand and freed right after, which
        keeps peak VRAM at max(encoders, unet) instead of their sum."""
        for prov in (self.accel, "CPUExecutionProvider"):
            try:
                return self._mk(path, prov)
            except Exception:
                continue
        return self._mk(path, "CPUExecutionProvider")

    @staticmethod
    def _pooled(out):
        for o in out[1:]:
            a = np.asarray(o)
            if a.ndim == 2:
                return a
        return None

    # ---- text
    def _run_te(self, sess, ids):
        inp = sess.get_inputs()[0]
        arr = np.asarray([ids])
        arr = arr.astype(np.int32) if "int32" in inp.type else \
            arr.astype(np.int64)
        return sess.run(None, {inp.name: arr})

    def encode(self, prompt):
        te = self._te_session(self.te_path)
        out = self._run_te(te, self.tok.encode(prompt))
        hidden = np.asarray(out[0], np.float32)
        pooled = self._pooled(out)
        del te
        if self.is_xl:
            te2 = self._te_session(self.te2_path)
            out2 = self._run_te(te2, self.tok2.encode(prompt))
            del te2
            hidden2 = np.asarray(out2[0], np.float32)
            pooled2 = self._pooled(out2)
            hidden = np.concatenate([hidden, hidden2], axis=-1)
            if pooled is not None and pooled2 is not None:
                pooled = np.concatenate([pooled, pooled2], axis=-1)
            else:
                pooled = pooled2 if pooled2 is not None else pooled
        return hidden, (None if pooled is None
                        else np.asarray(pooled, np.float32))

    def _unet_eps(self, unet, uinputs, sample, ti, hidden, tids,
                  neg_hidden=None, guidance=0.0):
        """UNet call. Classifier-free guidance is done as TWO sequential
        batch-1 passes rather than one batch-2 pass: on an 8 GB DirectML card
        the doubled activation batch is what tips the driver into an access
        violation. Two passes cost ~2x UNet time but always fit."""
        def run_once(h):
            base = {"sample": sample, "encoder_hidden_states": h}
            if "time_ids" in uinputs:
                base["time_ids"] = tids
            for name in uinputs:
                if name not in base:
                    base[name] = h
            out = None
            for ts in (np.asarray([ti], np.int64),
                       np.asarray([float(ti)], np.float32)):
                try:
                    feed = dict(base)
                    feed["timestep"] = ts
                    out = unet.run(None, feed)[0]
                    break
                except Exception:
                    continue
            if out is None:
                feed = dict(base)
                feed["timestep"] = np.asarray([ti], np.int64)
                out = unet.run(None, feed)[0]
            return np.asarray(out, np.float32)

        use_cfg = bool(neg_hidden is not None and guidance and guidance > 1.0)
        if use_cfg:
            e_un = run_once(neg_hidden)
            e_c = run_once(hidden)
            return (e_un + float(guidance) * (e_c - e_un)).astype(np.float32)
        return run_once(hidden)

    def _neg(self, negative, guidance):
        if negative and guidance and guidance > 1.0:
            return self.encode(negative)[0]
        return None

    # ---- denoise
    def generate(self, prompt, steps=4, seed=0, size=512, guidance=0.0,
                 negative=""):
        rng = np.random.default_rng(seed)
        sched = EulerScheduler(self.sched_cfg, steps=steps)
        lat_shape = (1, 4, size // 8, size // 8)
        lat = sched.scale(rng.standard_normal(lat_shape).astype(np.float32))
        hidden, pooled = self.encode(prompt)
        neg_hidden = self._neg(negative, guidance)
        # UNet session created here and freed right after the loop so peak
        # VRAM stays one model at a time (critical on an 8 GB card).
        unet = self._mk(self.unet_path, self.accel)
        uinputs = {i.name for i in unet.get_inputs()}
        tids = np.asarray([[size, size, 0, 0, size, size]], np.float32)
        for i in range(len(sched.timesteps)):
            ti = int(round(float(sched.timesteps[i])))
            eps = self._unet_eps(unet, uinputs, sched.scale_model_input(lat, i),
                                 ti, hidden, tids, neg_hidden, guidance)
            lat = sched.step(eps, lat, i, rng)
        del unet
        return self.decode(lat)

    # ---- multi-diffusion: tiled high-res with per-tile prompts
    def generate_tiled(self, prompt, size=1024, tile=512, stride=256,
                       steps=4, seed=0, tile_prompts=None, log=None,
                       negative="", guidance=0.0):
        """Denoise one shared latent, but run the UNet per tile (with an
        optional tile-specific prompt) and blend the overlapping noise
        predictions. Coherent full image, detailed region by region."""
        lh = lw = int(size) // 8
        tl = min(int(tile) // 8, lh)
        sl = max(1, int(stride) // 8)
        rng = np.random.default_rng(seed)
        sched = EulerScheduler(self.sched_cfg, steps=steps)
        lat = sched.scale(rng.standard_normal((1, 4, lh, lw)).astype(np.float32))

        ys = list(range(0, max(1, lh - tl + 1), sl))
        xs = list(range(0, max(1, lw - tl + 1), sl))
        if ys[-1] != lh - tl:
            ys.append(lh - tl)
        if xs[-1] != lw - tl:
            xs.append(lw - tl)
        ys, xs = sorted(set(ys)), sorted(set(xs))
        tiles = [(x, y) for y in ys for x in xs]
        if log:
            log(f"tiled {size}px: {len(tiles)} tiles ({len(xs)}x{len(ys)}), "
                f"latent {lh}x{lw}, tile {tl}")

        base = self.encode(prompt)
        neg_hidden = self._neg(negative, guidance)
        emb = {}
        if tile_prompts:
            for (x, y) in tiles:
                p = (tile_prompts.get((x, y))
                     or tile_prompts.get(f"{x},{y}") or prompt)
                emb[(x, y)] = self.encode(p)
        unet = self._mk(self.unet_path, self.accel)
        uinputs = {i.name for i in unet.get_inputs()}
        tids = np.asarray([[size, size, 0, 0, size, size]], np.float32)
        for i in range(len(sched.timesteps)):
            ti = int(round(float(sched.timesteps[i])))
            acc = np.zeros_like(lat)
            wsum = np.zeros((1, 1, lh, lw), np.float32)
            for (x, y) in tiles:
                crop = lat[:, :, y:y + tl, x:x + tl]
                hidden, pooled = emb.get((x, y), base)
                eps = self._unet_eps(
                    unet, uinputs, sched.scale_model_input(crop, i), ti,
                    hidden, tids, neg_hidden, guidance)
                acc[:, :, y:y + tl, x:x + tl] += np.asarray(eps, np.float32)
                wsum[:, :, y:y + tl, x:x + tl] += 1.0
            lat = sched.step(acc / np.maximum(wsum, 1e-6), lat, i, rng)
            if log:
                log(f"  step {i+1}/{len(sched.timesteps)} done")
        del unet
        return self.decode(lat)

    # ---- img2img / tile upscale (keeps one coherent subject)
    def encode_image(self, img, sess=None):
        a = np.asarray(img, np.float32) / 127.5 - 1.0
        t = a.transpose(2, 0, 1)[None].astype(np.float32)
        s = sess or self._mk(self.vae_enc_path, self.accel)
        z = s.run(None, {s.get_inputs()[0].name: t})[0]
        if sess is None:
            del s
        return (np.asarray(z, np.float32) * self.scale)

    def decode_with(self, z, sess):
        zz = (z / self.scale).astype(np.float32)
        img = np.asarray(sess.run(None, {sess.get_inputs()[0].name: zz})[0],
                         np.float32)
        img = (img / 2.0 + 0.5).clip(0, 1)
        return (img[0].transpose(1, 2, 0) * 255).astype(np.uint8)

    def img2img_latent(self, z0, prompt, strength=0.4, steps=3, seed=0,
                       unet=None, hidden=None, neg_hidden=None, negative="",
                       guidance=0.0):
        rng = np.random.default_rng(seed)
        sched = EulerScheduler(self.sched_cfg, steps=steps)
        k = max(steps - int(round(steps * float(strength))), 0)
        # Embeddings must be ready BEFORE the UNet session is open: creating
        # a text-encoder session while the UNet session is alive means two
        # DirectML sessions at once, which crashes on an 8 GB card.
        if hidden is None:
            hidden, _ = self.encode(prompt)
        if neg_hidden is None:
            neg_hidden = self._neg(negative, guidance)
        own = unet is None
        unet = unet or self._mk(self.unet_path, self.accel)
        uinputs = {i.name for i in unet.get_inputs()}
        h8 = z0.shape[-2] * 8
        tids = np.asarray([[h8, h8, 0, 0, h8, h8]], np.float32)
        z = (z0 + rng.standard_normal(z0.shape).astype(np.float32)
             * sched.sigmas[k]).astype(np.float32)
        for i in range(k, steps):
            ti = int(round(float(sched.timesteps[i])))
            eps = self._unet_eps(unet, uinputs, sched.scale_model_input(z, i),
                                 ti, hidden, tids, neg_hidden, guidance)
            z = sched.step(eps, z, i, rng)
        if own:
            del unet
        return z

    def tile_upscale(self, img, prompt, scale=2, tile=512, overlap=128,
                     strength=0.4, steps=3, seed=0, log=None, negative="",
                     guidance=0.0):
        """Enlarge a (coherent) image and finish each tile in detail with
        img2img, then blend. Because every tile starts from the same
        coherent base, the result stays one picture - no collage, no seams.

        Sessions are used one at a time (encode all -> denoise all -> decode
        all): holding the UNet + VAE encoder + VAE decoder open together
        exhausts an 8 GB card and crashes DirectML."""
        from PIL import Image
        im = Image.fromarray(np.asarray(img, np.uint8))
        W, H = im.size
        arr = np.asarray(im.resize((W * scale, H * scale), Image.LANCZOS),
                         np.uint8)
        BH, BW = arr.shape[:2]
        step = max(1, tile - overlap)
        boxes = []
        for y in range(0, BH, step):
            for x in range(0, BW, step):
                y1, x1 = min(y + tile, BH), min(x + tile, BW)
                y0, x0 = max(0, y1 - tile), max(0, x1 - tile)
                boxes.append((x0, y0, x1, y1))
        if log:
            log(f"  {len(boxes)} tiles, one session at a time")
        # 1. encode every tile. The VAE encoder is small and used once per
        #    tile, so it runs on CPU - that leaves the whole 8 GB of VRAM
        #    for the UNet and avoids a DirectML OOM when the UNet session is
        #    created right after the encoder session is freed.
        import gc
        venc = self._mk(self.vae_enc_path, "CPUExecutionProvider")
        latents = [self.encode_image(arr[y0:y1, x0:x1], sess=venc)
                   for (x0, y0, x1, y1) in boxes]
        del venc
        gc.collect()
        # 2. denoise every tile (UNet only). All embeddings are computed
        #    first so no text-encoder session is open beside the UNet.
        hidden, _ = self.encode(prompt)
        neg_hidden = self._neg(negative, guidance)
        unet = self._mk(self.unet_path, self.accel)
        zs = [self.img2img_latent(z0, prompt, strength=strength, steps=steps,
                                  seed=seed + x0 * 7 + y0 * 13, unet=unet,
                                  hidden=hidden, neg_hidden=neg_hidden,
                                  negative=negative, guidance=guidance)
              for z0 in latents]
        del unet
        gc.collect()
        # 3. decode every tile (VAE decoder only)
        vdec = self._mk(self.vae_path, self.accel)
        outs = [self.decode_with(z, vdec) for z in zs]
        del vdec
        gc.collect()
        # 4. blend with a feathered window
        acc = np.zeros((BH, BW, 3), np.float32)
        wsum = np.zeros((BH, BW, 1), np.float32)
        for (x0, y0, x1, y1), out in zip(boxes, outs):
            ch, cw = y1 - y0, x1 - x0
            if out.shape[:2] != (ch, cw):
                out = np.asarray(Image.fromarray(out).resize(
                    (cw, ch), Image.LANCZOS), np.uint8)
            win = _feather(ch, cw, overlap)[..., None]
            acc[y0:y1, x0:x1] += out.astype(np.float32) * win
            wsum[y0:y1, x0:x1] += win
        return np.clip(acc / np.maximum(wsum, 1e-6), 0, 255).astype(np.uint8)

    def character_sheet(self, img, prompt, views=("front", "side", "back"),
                        strength=0.55, steps=20, seed=0, guidance=7.0,
                        negative="", log=None):
        """Turn one character image into a turnaround. The other views are
        derived with img2img from the same base, so colours and silhouette
        stay consistent. One session at a time, as always."""
        import gc
        base = np.asarray(img, np.uint8)
        out = {"front": base}
        want = [v for v in views if v != "front"]
        if not want:
            return out
        venc = self._mk(self.vae_enc_path, "CPUExecutionProvider")
        z0 = self.encode_image(base, sess=venc)
        del venc
        gc.collect()
        VIEW_PROMPT = {
            "side": ", full body side view, profile, facing left",
            "back": ", full body back view, seen from behind, no face "
                    "visible, back of the cloak",
            "three-quarter": ", full body three-quarter view",
        }
        for v in want:
            vp = prompt + VIEW_PROMPT.get(v, f", {v} view")
            hidden, _ = self.encode(vp)
            neg_hidden = self._neg(negative, guidance)
            unet = self._mk(self.unet_path, self.accel)
            z = self.img2img_latent(z0, vp, strength=strength, steps=steps,
                                    seed=seed + (7 if v == "side" else 23),
                                    unet=unet, hidden=hidden,
                                    neg_hidden=neg_hidden, guidance=guidance)
            del unet
            gc.collect()
            vdec = self._mk(self.vae_path, self.accel)
            out[v] = self.decode_with(z, vdec)
            del vdec
            gc.collect()
            if log:
                log(f"  view done: {v}")
        return out

    # ---- vae (tiled)
    def decode(self, lat):
        lat = (lat / self.scale).astype(np.float32)
        vae = self._mk(self.vae_path, self.accel)
        inp = vae.get_inputs()[0].name
        try:
            img = vae.run(None, {inp: lat})[0]
        except Exception:
            img = self._decode_tiled(vae, lat, inp)
        del vae
        img = np.asarray(img, np.float32)
        img = (img / 2.0 + 0.5).clip(0, 1)
        img = (img[0].transpose(1, 2, 0) * 255).astype(np.uint8)
        return img

    def _decode_tiled(self, vae, lat, inp, tile=64, overlap=8):
        _, _, h, w = lat.shape
        out = None
        for y in range(0, h, tile - overlap):
            for x in range(0, w, tile - overlap):
                y1, x1 = min(y + tile, h), min(x + tile, w)
                part = lat[:, :, y:y1, x:x1]
                dec = np.asarray(vae.run(None, {inp: part})[0], np.float32)
                if out is None:
                    out = np.zeros((1, 3, h * 8, w * 8), np.float32)
                out[:, :, y * 8:y1 * 8, x * 8:x1 * 8] = dec
        return out


# --------------------------------------------------------------- dispatch
_CACHE = {}


def _model_dir(name):
    root = os.path.join(os.path.expanduser("~"), ".rox", "ml", "models")
    return os.path.join(root, name)


def get_pipeline(name="sd-turbo", accel="DmlExecutionProvider"):
    key = (name, accel)
    if key not in _CACHE:
        _CACHE[key] = SD(_model_dir(name), accel=accel)
    return _CACHE[key]


def _label(img, text):
    from PIL import Image, ImageDraw
    im = Image.fromarray(np.asarray(img, np.uint8)).convert("RGB")
    dr = ImageDraw.Draw(im)
    h = 26
    dr.rectangle([0, im.height - h, im.width, im.height], fill=(0, 0, 0))
    dr.text((8, im.height - h + 6), text, fill=(235, 235, 235))
    return im


def compose_sheet(views, out_path, order=("front", "side", "back")):
    """Lay the turnaround views side by side into one labelled sheet."""
    from PIL import Image
    ims = [_label(views[k], k.upper()) for k in order if k in views]
    if not ims:
        return None
    h = max(i.height for i in ims)
    w = sum(i.width for i in ims)
    sheet = Image.new("RGB", (w, h), (24, 24, 28))
    x = 0
    for im in ims:
        sheet.paste(im, (x, 0))
        x += im.width
    sheet.save(out_path)
    return out_path


def dispatch(op, req):
    if op == "sd_generate":
        name = req.get("model", "sd-turbo")
        accel = req.get("accel", "DmlExecutionProvider")
        try:
            pipe = get_pipeline(name, accel)
        except Exception as e:
            return {"ok": False, "error": f"load {name}: {str(e)[:300]}"}
        img = pipe.generate(req.get("prompt", ""),
                            steps=int(req.get("steps", 4)),
                            seed=int(req.get("seed", 0)),
                            size=int(req.get("size", 512)),
                            guidance=float(req.get("guidance", 0.0)),
                            negative=req.get("negative", ""))
        out = req.get("out")
        if out:
            from PIL import Image
            Image.fromarray(img).save(out)
            return {"ok": True, "path": out, "size": list(img.shape[:2]),
                    "model": name}
        return {"ok": True, "image_b64": _b64(img), "model": name}

    if op == "sd_generate_tiled":
        name = req.get("model", "sd-turbo-ort")
        accel = req.get("accel", "DmlExecutionProvider")
        try:
            pipe = get_pipeline(name, accel)
        except Exception as e:
            return {"ok": False, "error": f"load {name}: {str(e)[:300]}"}
        logpath = req.get("log")

        def _log(m):
            if not logpath:
                return
            try:
                with open(logpath, "a", encoding="utf-8") as f:
                    f.write(str(m) + "\n")
            except Exception:
                pass

        tp = req.get("tile_prompts") or None
        if tp:
            tp = {(int(k.split(",")[0]), int(k.split(",")[1])): v
                  for k, v in tp.items()}
        img = pipe.generate_tiled(
            req.get("prompt", ""), size=int(req.get("size", 1024)),
            tile=int(req.get("tile", 512)), stride=int(req.get("stride", 256)),
            steps=int(req.get("steps", 4)), seed=int(req.get("seed", 0)),
            tile_prompts=tp, log=_log,
            negative=req.get("negative", ""),
            guidance=float(req.get("guidance", 0.0)))
        out = req.get("out")
        if out:
            from PIL import Image
            Image.fromarray(img).save(out)
            return {"ok": True, "path": out, "size": list(img.shape[:2]),
                    "model": name}
        return {"ok": True, "image_b64": _b64(img), "model": name}

    if op in ("sd_tile_upscale", "sd_generate_hd"):
        name = req.get("model", "sd-turbo-ort")
        accel = req.get("accel", "DmlExecutionProvider")
        try:
            pipe = get_pipeline(name, accel)
        except Exception as e:
            return {"ok": False, "error": f"load {name}: {str(e)[:300]}"}
        logpath = req.get("log")

        def _log(m):
            if not logpath:
                return
            try:
                with open(logpath, "a", encoding="utf-8") as f:
                    f.write(str(m) + "\n")
            except Exception:
                pass

        prompt = req.get("prompt", "")
        if op == "sd_generate_hd":
            base = int(req.get("base", 512))
            target = int(req.get("size", 1024))
            img = pipe.generate(prompt, steps=int(req.get("steps", 4)),
                                seed=int(req.get("seed", 0)), size=base,
                                guidance=float(req.get("guidance", 0.0)),
                                negative=req.get("negative", ""))
            _log(f"base {base}px done -> tile-upscale to {target}")
        else:
            from PIL import Image
            img = np.asarray(Image.open(req["in"]).convert("RGB"), np.uint8)
            target = int(req.get("size", img.shape[0] * 2))
        scale = max(1, int(round(target / float(img.shape[0]))))
        img = pipe.tile_upscale(
            img, prompt, scale=scale, tile=int(req.get("tile", 512)),
            overlap=int(req.get("overlap", 128)),
            strength=float(req.get("strength", 0.4)),
            steps=int(req.get("up_steps", 3)),
            seed=int(req.get("seed", 0)) + 1, log=_log,
            negative=req.get("negative", ""),
            guidance=float(req.get("guidance", 0.0)))
        out = req.get("out")
        if out:
            from PIL import Image
            Image.fromarray(img).save(out)
            return {"ok": True, "path": out, "size": list(img.shape[:2]),
                    "model": name}
        return {"ok": True, "image_b64": _b64(img), "model": name}

    if op == "sd_character_sheet":
        name = req.get("model", "dreamshaper8-ort")
        accel = req.get("accel", "DmlExecutionProvider")
        try:
            pipe = get_pipeline(name, accel)
        except Exception as e:
            return {"ok": False, "error": f"load {name}: {str(e)[:300]}"}
        from PIL import Image
        src = req.get("in")
        if not src or not os.path.exists(src):
            return {"ok": False, "error": "input image required"}
        img = np.asarray(Image.open(src).convert("RGB"), np.uint8)
        logpath = req.get("log")

        def _log(m):
            if not logpath:
                return
            try:
                with open(logpath, "a", encoding="utf-8") as f:
                    f.write(str(m) + "\n")
            except Exception:
                pass

        views = pipe.character_sheet(
            img, req.get("prompt", ""),
            strength=float(req.get("strength", 0.55)),
            steps=int(req.get("steps", 20)), seed=int(req.get("seed", 0)),
            guidance=float(req.get("guidance", 7.0)),
            negative=req.get("negative", ""), log=_log)
        outdir = req.get("outdir") or os.path.dirname(src)
        base = os.path.splitext(os.path.basename(src))[0]
        files = {}
        for k, v in views.items():
            p = os.path.join(outdir, f"{base}-{k}.png")
            Image.fromarray(np.asarray(v, np.uint8)).save(p)
            files[k] = p
        order = req.get("order") or ("front", "side", "back")
        sheet = req.get("out") or os.path.join(outdir, f"{base}-sheet.png")
        compose_sheet(views, sheet, order=tuple(order))
        files["sheet"] = sheet
        return {"ok": True, "files": files, "sheet": sheet, "model": name}

    return {"ok": False, "error": f"unknown op {op}"}


def _b64(arr):
    import base64
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()
