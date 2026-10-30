// Coal desktop launcher (Go).
//
// Resolves the API configuration, validates prerequisites, and launches the
// Rust/Tauri shell. Running this is all a user needs to do:
//
//   coal-launcher.exe
//
// Key resolution order:
//   1. NEBIUS_API_KEY in the environment
//   2. %USERPROFILE%\.coal\nebius.key  (one line, no quotes)
package main

import (
	"bufio"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

const (
	defaultBase  = "https://api.studio.nebius.com/v1"
	defaultModel = "nvidia/nemotron-3-super-120b-a12b"
)

func exists(p string) bool {
	_, err := os.Stat(p)
	return err == nil
}

func have(cmd string, args ...string) bool {
	c := exec.Command(cmd, args...)
	c.Stdout = nil
	c.Stderr = nil
	return c.Run() == nil
}

// readKey looks for the key in the environment, then in ~/.coal/nebius.key.
func readKey() string {
	if k := strings.TrimSpace(os.Getenv("NEBIUS_API_KEY")); k != "" {
		return k
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return ""
	}
	b, err := os.ReadFile(filepath.Join(home, ".coal", "nebius.key"))
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(b))
}

// coalDir resolves the Python agent directory.
func coalDir() string {
	if d := os.Getenv("COAL_DIR"); d != "" {
		return d
	}
	exe, _ := os.Executable()
	base := filepath.Dir(exe)
	// the launcher may sit in desktop/ or desktop/launcher/ - probe both
	cands := []string{
		filepath.Join(base, "..", "..", "agent"),
		filepath.Join(base, "..", "agent"),
		filepath.Join(base, "agent"),
	}
	for _, c := range cands {
		c = filepath.Clean(c)
		if exists(filepath.Join(c, "coal.py")) {
			return c
		}
	}
	return filepath.Clean(cands[0])
}

func main() {
	here, _ := os.Executable()
	base := filepath.Dir(here)

	exe := filepath.Join(base, "coal-desktop.exe")
	if !exists(exe) {
		for _, cand := range []string{
			filepath.Join(base, "..", "src-tauri", "target", "release", "coal-desktop.exe"),
			filepath.Join(base, "..", "src-tauri", "target", "debug", "coal-desktop.exe"),
		} {
			if exists(cand) {
				exe = cand
				break
			}
		}
	}
	if !exists(exe) {
		fmt.Println("[!] coal-desktop.exe not found.")
		fmt.Println("    build it:  desktop\\build.cmd")
		os.Exit(1)
	}

	dir := coalDir()
	if !exists(filepath.Join(dir, "coal.py")) {
		fmt.Printf("[!] agent not found at %s\n", dir)
		fmt.Println("    set COAL_DIR to the agent directory")
		os.Exit(1)
	}

	if !have("py", "-3.15", "--version") && !have("python", "--version") {
		fmt.Println("[!] no Python found (need py -3.15 or python on PATH)")
		os.Exit(1)
	}

	env := append([]string{}, os.Environ()...)
	env = append(env, "COAL_NO_35B=1", "COAL_DIR="+dir)

	key := readKey()
	if key != "" {
		env = append(env, "NEBIUS_API_KEY="+key)
		base := os.Getenv("COAL_BASE_URL")
		if base == "" {
			base = defaultBase
			env = append(env, "COAL_BASE_URL="+defaultBase)
		}
		model := os.Getenv("COAL_AGENT_MODEL")
		if model == "" {
			model = defaultModel
			env = append(env, "COAL_AGENT_MODEL="+defaultModel)
		}
		fmt.Printf("[i] provider : nebius\n")
		fmt.Printf("[i] endpoint : %s\n", base)
		fmt.Printf("[i] model    : %s\n", model)
	} else {
		fmt.Println("[i] no NEBIUS_API_KEY and no ~/.coal/nebius.key")
		fmt.Println("    falling back to the local model")
	}

	fmt.Printf("[i] agent dir: %s\n", dir)
	fmt.Printf("[i] launching: %s\n", exe)

	cmd := exec.Command(exe)
	cmd.Dir = filepath.Dir(exe)
	cmd.Env = env
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Start(); err != nil {
		fmt.Println("[!] launch failed:", err)
		os.Exit(1)
	}

	if err := cmd.Wait(); err != nil {
		fmt.Println("[i] app exited:", err)
		reader := bufio.NewReader(os.Stdin)
		fmt.Print("press enter to close...")
		_, _ = reader.ReadString('\n')
		os.Exit(1)
	}
}
