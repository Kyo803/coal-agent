// ROX N desktop launcher (Go).
//
// Validates the runtime prerequisites and launches the Rust/Tauri shell.
// Keeping this in Go gives one obvious entry point and a place to fail with a
// useful message instead of a silent empty window.
package main

import (
	"bufio"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
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

// roxDir resolves the Python agent directory.
func roxDir() string {
	if d := os.Getenv("ROX_DIR"); d != "" {
		return d
	}
	exe, _ := os.Executable()
	base := filepath.Dir(exe)
	// the launcher may sit in desktop/ or desktop/launcher/ - probe both
	cands := []string{
		filepath.Join(base, "..", "..", "lm_track", "rox_chat"),
		filepath.Join(base, "..", "lm_track", "rox_chat"),
		filepath.Join(base, "lm_track", "rox_chat"),
	}
	for _, c := range cands {
		c = filepath.Clean(c)
		if exists(filepath.Join(c, "rox.py")) {
			return c
		}
	}
	return filepath.Clean(cands[0])
}

func main() {
	here, _ := os.Executable()
	base := filepath.Dir(here)

	exe := filepath.Join(base, "rox-n-desktop.exe")
	if !exists(exe) {
		// common build locations
		for _, cand := range []string{
			filepath.Join(base, "..", "src-tauri", "target", "debug", "rox-n-desktop.exe"),
			filepath.Join(base, "..", "src-tauri", "target", "release", "rox-n-desktop.exe"),
		} {
			if exists(cand) {
				exe = cand
				break
			}
		}
	}
	if !exists(exe) {
		fmt.Println("[!] rox-n-desktop.exe not found.")
		fmt.Println("    build it:  cd desktop\\src-tauri && cargo build")
		os.Exit(1)
	}

	dir := roxDir()
	if !exists(filepath.Join(dir, "rox.py")) {
		fmt.Printf("[!] agent not found at %s\n", dir)
		fmt.Println("    set ROX_DIR to the lm_track/rox_chat directory")
		os.Exit(1)
	}

	if !have("py", "-3.15", "--version") && !have("python", "--version") {
		fmt.Println("[!] no Python found (need py -3.15 or python on PATH)")
		os.Exit(1)
	}

	if os.Getenv("NEBIUS_API_KEY") == "" {
		fmt.Println("[i] NEBIUS_API_KEY not set - the agent will use the local model.")
	}
	fmt.Printf("[i] agent dir: %s\n", dir)
	fmt.Printf("[i] launching:  %s\n", exe)

	cmd := exec.Command(exe)
	cmd.Dir = filepath.Dir(exe)
	cmd.Env = append(os.Environ(),
		"ROX_NO_35B=1",
		"ROX_DIR="+dir,
	)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Start(); err != nil {
		fmt.Println("[!] launch failed:", err)
		os.Exit(1)
	}

	if err := cmd.Wait(); err != nil {
		// keep the console open on a crash so the message is readable
		fmt.Println("[i] app exited:", err)
		reader := bufio.NewReader(os.Stdin)
		fmt.Print("press enter to close...")
		_, _ = reader.ReadString('\n')
		os.Exit(1)
	}
}
