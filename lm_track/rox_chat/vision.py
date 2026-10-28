"""ROX N vision: send images to the local model (Qwen3.6 vision via mmproj).

The server must be started with --mmproj (server_manager does this when
cfg.model.vision is true). Images are sent as OpenAI-style content
arrays, which llama-server converts to the Qwen <|vision_start|> format.

  from vision import encode_image, ask_about_image
  url = encode_image("screenshot.png")
  answer = ask_about_image("screenshot.png", "what error is shown?")
"""
import base64
import json
import mimetypes
import os
import urllib.request

from rox_config import cfg

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp"}


def encode_image(path):
    """Return a data URL (base64) for the image at path."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    ext = os.path.splitext(path)[1].lower()
    mime = MIME.get(ext) or mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def vision_enabled():
    return bool(cfg.model.get("vision")) and bool(
        cfg.mmproj_path() and os.path.exists(cfg.mmproj_path()))


def build_message(image_paths, question):
    content = [{"type": "text", "text": question}]
    for p in image_paths:
        content.append({"type": "image_url",
                        "image_url": {"url": encode_image(p)}})
    return {"role": "user", "content": content}


def ask_about_image(image_paths, question, base_url=None, model=None,
                    max_tokens=768, timeout=600):
    """Send one or more images + a question to the local model."""
    if isinstance(image_paths, str):
        image_paths = [image_paths]
    base = (base_url or cfg.base_url).rstrip("/")
    payload = {
        "model": model or "local-model",
        "messages": [build_message(image_paths, question)],
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read().decode())
    return out["choices"][0]["message"].get("content", "")


if __name__ == "__main__":
    import tempfile
    # make a tiny valid PNG (1x1 red) to smoke-test the pipeline wiring
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4"
        "nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC")
    p = os.path.join(tempfile.mkdtemp(), "t.png")
    open(p, "wb").write(png)
    print("vision enabled:", vision_enabled())
    print("encoded prefix:", encode_image(p)[:40])
    if vision_enabled():
        try:
            print("answer:", ask_about_image(p, "What colour is this?")[:120])
        except Exception as e:
            print("model error (server may lack --mmproj):", e)
    else:
        print("server not started with --mmproj; restart via "
              "server_manager to enable vision")
