// Coal — terminal chat UI (OpenCode-style layout).
//
// It drives `coal.py --json-repl`: one long-lived agent session, one JSON
// object per prompt on stdin and newline-delimited events on stdout.
package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/textinput"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

// ---------------------------------------------------------------- events
type event struct {
	T       string         `json:"t"`
	Text    string         `json:"text"`
	Prompt  string         `json:"prompt"`
	Model   string         `json:"model"`
	Name    string         `json:"name"`
	Args    map[string]any `json:"args"`
	Output  string         `json:"output"`
	Message string         `json:"message"`
	MS      int            `json:"ms"`
	Kind    string         `json:"kind"`
	Personality string     `json:"personality"`
	LLM     struct {
		Provider string `json:"provider"`
		Model    string `json:"model"`
	} `json:"llm"`
}

type entryKind int

const (
	kUser entryKind = iota
	kAssistant
	kTool
	kThinking
	kError
	kInfo
)

type entry struct {
	kind  entryKind
	text  string
	name  string
	extra string
}

type eventMsg event
type childClosedMsg struct{}
type tickMsg time.Time
type envMsg struct {
	backend string
	err     string
}
type installMsg struct{ err string }

// ---------------------------------------------------------------- styles
var (
	accent   = lipgloss.AdaptiveColor{Light: "#0B6E99", Dark: "#5FD7FF"}
	dim      = lipgloss.AdaptiveColor{Light: "#6C6C6C", Dark: "#8A8A8A"}
	good     = lipgloss.AdaptiveColor{Light: "#2E7D32", Dark: "#5FD75F"}
	bad      = lipgloss.AdaptiveColor{Light: "#B00020", Dark: "#FF6B6B"}
	userCol  = lipgloss.AdaptiveColor{Light: "#0B6E99", Dark: "#7DDEFF"}

	titleStyle  = lipgloss.NewStyle().Bold(true).Foreground(accent)
	dimStyle    = lipgloss.NewStyle().Foreground(dim)
	userStyle   = lipgloss.NewStyle().Foreground(userCol).Bold(true)
	asstStyle   = lipgloss.NewStyle()
	toolStyle   = lipgloss.NewStyle().Foreground(good).Bold(true)
	toolOutStyle = lipgloss.NewStyle().Foreground(dim)
	errStyle    = lipgloss.NewStyle().Foreground(bad)
	thinkStyle  = lipgloss.NewStyle().Foreground(dim).Italic(true)
	boxStyle    = lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).
			BorderForeground(accent).Padding(0, 1)
	statusStyle = lipgloss.NewStyle().Foreground(dim)
)

// ---------------------------------------------------------------- model
type model struct {
	w, h    int
	ready   bool
	entries []entry
	vp      viewport.Model
	input   textinput.Model

	ch     chan event
	stdin  io.WriteCloser
	cmd    *exec.Cmd
	pyside string

	busy      bool
	status    string
	modelName string
	persona   string
	started   time.Time
	lastMS    int
	quitting  bool

	showThinking bool
	showToolOut  bool
	backend      string
	wslKnown     bool
	wslOK        bool
	banner       string
}

func newModel(roxChat string) model {
	ti := textinput.New()
	ti.Placeholder = "Ask Coal…"
	ti.Focus()
	ti.CharLimit = 4000
	ti.Prompt = "› "
	ti.PromptStyle = lipgloss.NewStyle().Foreground(accent).Bold(true)

	m := model{input: ti, status: "starting", pyside: roxChat,
		showThinking: true, showToolOut: true}
	m.ch = make(chan event, 256)
	m.startChild()
	return m
}

func checkEnv(roxChat string) tea.Cmd {
	return func() tea.Msg {
		c := exec.Command("py", "-3.15", "-c",
			"import json;from chipflow import backend;"+
				"print(json.dumps(backend.report()))")
		c.Dir = roxChat
		c.Env = append(os.Environ(), "COAL_NO_35B=1")
		out, err := c.Output()
		if err != nil {
			return envMsg{err: err.Error()}
		}
		var r struct {
			Backend string `json:"backend"`
		}
		_ = json.Unmarshal(out, &r)
		return envMsg{backend: r.Backend}
	}
}

func wslAttempted() bool {
	home, err := os.UserHomeDir()
	if err != nil {
		return true
	}
	_, statErr := os.Stat(filepath.Join(home, ".coal", "wsl_install_attempted"))
	return statErr == nil
}

func markWslAttempted() {
	home, err := os.UserHomeDir()
	if err != nil {
		return
	}
	p := filepath.Join(home, ".coal", "wsl_install_attempted")
	_ = os.MkdirAll(filepath.Dir(p), 0o755)
	_ = os.WriteFile(p, []byte(time.Now().Format(time.RFC3339)), 0o644)
}

func installWSL(roxChat string) tea.Cmd {
	return func() tea.Msg {
		script := filepath.Join(roxChat, "setup_wsl.ps1")
		arg := fmt.Sprintf(
			"Start-Process powershell -Verb RunAs -ArgumentList "+
				"'-ExecutionPolicy','Bypass','-NoProfile','-File','%s'", script)
		c := exec.Command("powershell", "-NoProfile", "-Command", arg)
		if err := c.Run(); err != nil {
			return installMsg{err: err.Error()}
		}
		return installMsg{}
	}
}

func (m *model) startChild() {
	cmd := exec.Command("py", "-3.15", "coal.py", "--json-repl")
	cmd.Dir = m.pyside
	// never let the chat session try to load the 19.7 GB 35B model
	cmd.Env = append(os.Environ(), "COAL_NO_35B=1")
	out, err := cmd.StdoutPipe()
	if err != nil {
		m.status = "error: " + err.Error()
		return
	}
	in, err := cmd.StdinPipe()
	if err != nil {
		m.status = "error: " + err.Error()
		return
	}
	cmd.Stderr = io.Discard
	if err := cmd.Start(); err != nil {
		m.status = "error: " + err.Error()
		return
	}
	m.cmd = cmd
	m.stdin = in
	go func(r io.Reader) {
		sc := bufio.NewScanner(r)
		sc.Buffer(make([]byte, 0, 64*1024), 4*1024*1024)
		for sc.Scan() {
			line := strings.TrimSpace(sc.Text())
			if line == "" {
				continue
			}
			var e event
			if json.Unmarshal([]byte(line), &e) == nil {
				m.ch <- e
			}
		}
		close(m.ch)
	}(out)
}

func waitForEvent(ch chan event) tea.Cmd {
	return func() tea.Msg {
		e, ok := <-ch
		if !ok {
			return childClosedMsg{}
		}
		return eventMsg(e)
	}
}

func tick() tea.Cmd {
	return tea.Tick(time.Second, func(t time.Time) tea.Msg { return tickMsg(t) })
}

func (m model) sendPrompt(text string) tea.Cmd {
	return func() tea.Msg {
		if m.stdin == nil {
			return nil
		}
		b, _ := json.Marshal(map[string]string{"prompt": text})
		m.stdin.Write(append(b, '\n'))
		return nil
	}
}

// ---------------------------------------------------------------- init
func (m model) Init() tea.Cmd {
	return tea.Batch(waitForEvent(m.ch), tick(), checkEnv(m.pyside))
}

// ---------------------------------------------------------------- update
func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.w, m.h = msg.Width, msg.Height
		vh := msg.Height - 8 - m.bannerLines()
		if vh < 3 {
			vh = 3
		}
		if !m.ready {
			m.vp = viewport.New(msg.Width, vh)
			m.ready = true
		} else {
			m.vp.Width = msg.Width
			m.vp.Height = vh
		}
		m.input.Width = msg.Width - 6
		m.refresh()
		return m, nil

	case envMsg:
		m.wslKnown = true
		m.wslOK = msg.backend == "wsl"
		m.backend = msg.backend
		if !m.wslOK {
			if !wslAttempted() {
				markWslAttempted()
				m.banner = "WSL toolchain missing — installing automatically " +
					"(approve the UAC prompt)…"
				return m, installWSL(m.pyside)
			}
			m.banner = "WSL toolchain not detected (" + orDash(msg.backend) +
				") — ctrl+w to install"
		} else {
			m.banner = ""
		}
		return m, nil

	case installMsg:
		if msg.err != "" {
			m.banner = "WSL install failed: " + msg.err
		} else {
			m.banner = "WSL installer launched — reboot when it asks"
		}
		return m, nil

	case tickMsg:
		if m.busy {
			return m, tick()
		}
		return m, nil

	case childClosedMsg:
		if !m.quitting {
			m.entries = append(m.entries, entry{kind: kError,
				text: "session ended"})
			m.status = "offline"
			m.busy = false
			m.refresh()
		}
		return m, nil

	case eventMsg:
		e := event(msg)
		switch e.T {
		case "ready":
			m.modelName = e.Model
			m.persona = e.Personality
			if e.LLM.Provider != "" {
				m.modelName = e.LLM.Provider + " · " + e.LLM.Model
			}
			m.status = "idle"
		case "start":
			m.busy = true
			m.started = time.Now()
			m.status = "thinking"
			m.entries = append(m.entries, entry{kind: kAssistant})
		case "thinking":
			if n := len(m.entries); n > 0 && m.entries[n-1].kind == kAssistant &&
				strings.TrimSpace(m.entries[n-1].text) == "" {
				m.entries[n-1] = entry{kind: kThinking, text: e.Text}
			} else {
				m.entries = append(m.entries, entry{kind: kThinking, text: e.Text})
				m.entries = append(m.entries, entry{kind: kAssistant})
			}
		case "token":
			if n := len(m.entries); n > 0 && m.entries[n-1].kind == kAssistant {
				m.entries[n-1].text += e.Text
			} else {
				m.entries = append(m.entries, entry{kind: kAssistant, text: e.Text})
			}
			m.status = "streaming"
		case "tool":
			nm := e.Name
			if len(e.Args) > 0 {
				var parts []string
				for k, v := range e.Args {
					parts = append(parts, fmt.Sprintf("%s=%v", k, v))
				}
				if len(parts) > 0 {
					nm += "(" + strings.Join(parts, ", ") + ")"
				}
			}
			m.entries = append(m.entries, entry{kind: kTool, name: nm,
				extra: e.Output})
			m.status = "tool: " + e.Name
		case "answer":
			if n := len(m.entries); n > 0 && m.entries[n-1].kind == kAssistant &&
				strings.TrimSpace(m.entries[n-1].text) == "" {
				m.entries[n-1].text = e.Text
			} else if strings.TrimSpace(e.Text) != "" {
				m.entries = append(m.entries, entry{kind: kAssistant, text: e.Text})
			}
		case "done":
			m.busy = false
			m.lastMS = e.MS
			m.status = "idle"
		case "error":
			m.busy = false
			m.status = "error"
			m.entries = append(m.entries, entry{kind: kError, text: e.Message})
		}
		m.refresh()
		return m, waitForEvent(m.ch)

	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c":
			if m.busy {
				if m.cmd != nil && m.cmd.Process != nil {
					m.cmd.Process.Kill()
				}
				m.busy = false
				m.status = "interrupted"
				m.entries = append(m.entries, entry{kind: kInfo,
					text: "interrupted — session reset"})
				m.startChild()
				m.refresh()
				return m, waitForEvent(m.ch)
			}
			m.quitting = true
			return m, tea.Quit
		case "ctrl+d":
			m.quitting = true
			return m, tea.Quit
		case "esc":
			if m.busy {
				if m.cmd != nil && m.cmd.Process != nil {
					m.cmd.Process.Kill()
				}
				m.busy = false
				m.status = "interrupted"
				m.startChild()
				m.refresh()
				return m, waitForEvent(m.ch)
			}
			return m, nil
		case "ctrl+t":
			m.showThinking = !m.showThinking
			m.status = fmt.Sprintf("thinking %s",
				map[bool]string{true: "shown", false: "hidden"}[m.showThinking])
			m.refresh()
			return m, nil
		case "ctrl+o":
			m.showToolOut = !m.showToolOut
			m.status = fmt.Sprintf("tool output %s",
				map[bool]string{true: "shown", false: "hidden"}[m.showToolOut])
			m.refresh()
			return m, nil
		case "ctrl+w":
			if m.wslKnown && !m.wslOK {
				m.banner = "launching WSL installer (approve the UAC prompt)…"
				return m, installWSL(m.pyside)
			}
			return m, nil
		case "pgup":
			m.vp.LineUp(m.vp.Height / 2)
			return m, nil
		case "pgdown":
			m.vp.LineDown(m.vp.Height / 2)
			return m, nil
		case "enter":
			if m.busy {
				return m, nil
			}
			text := strings.TrimSpace(m.input.Value())
			if text == "" {
				return m, nil
			}
			m.input.SetValue("")
			m.entries = append(m.entries, entry{kind: kUser, text: text})
			m.busy = true
			m.started = time.Now()
			m.status = "thinking"
			m.refresh()
			m.vp.GotoBottom()
			return m, tea.Batch(m.sendPrompt(text), waitForEvent(m.ch))
		}
	}

	var cmd tea.Cmd
	m.input, cmd = m.input.Update(msg)
	return m, cmd
}

// ---------------------------------------------------------------- view
func (m *model) refresh() {
	if !m.ready {
		return
	}
	atBottom := m.vp.AtBottom()
	m.vp.SetContent(m.transcript())
	if atBottom {
		m.vp.GotoBottom()
	}
}

func trunc(s string, n int) string {
	s = strings.TrimSpace(s)
	if len([]rune(s)) <= n {
		return s
	}
	return string([]rune(s)[:n]) + "…"
}

func indentBlock(s string, n int) string {
	pad := strings.Repeat(" ", n)
	lines := strings.Split(strings.TrimRight(s, "\n"), "\n")
	for i := range lines {
		lines[i] = pad + lines[i]
	}
	return strings.Join(lines, "\n")
}

func (m *model) transcript() string {
	if len(m.entries) == 0 {
		return dimStyle.Render("  Ask Coal to design, verify, or explain a chip.\n" +
			"  e.g. \"build a UART loopback chip\"  ·  \"what did the last batch prove?\"")
	}
	w := m.vp.Width
	if w < 20 {
		w = 20
	}
	var b strings.Builder
	for _, e := range m.entries {
		var s string
		switch e.kind {
		case kUser:
			s = userStyle.Render("› ") + lipgloss.NewStyle().
				Width(w-2).Render(e.text)
		case kAssistant:
			if strings.TrimSpace(e.text) == "" {
				continue
			}
			s = asstStyle.Width(w).Render(e.text)
		case kTool:
			s = toolStyle.Render("⏺ " + trunc(e.name, w-4))
			if m.showToolOut && strings.TrimSpace(e.extra) != "" {
				s += "\n" + toolOutStyle.Render(
					indentBlock(trunc(e.extra, 600), 4))
			}
		case kThinking:
			if !m.showThinking {
				continue
			}
			s = thinkStyle.Width(w).Render(trunc(e.text, 800))
		case kError:
			s = errStyle.Render("✗ " + e.text)
		case kInfo:
			s = dimStyle.Render("· " + e.text)
		}
		b.WriteString(s)
		b.WriteString("\n\n")
	}
	return b.String()
}

func (m model) View() string {
	if !m.ready {
		return "starting Coal…"
	}
	w := m.w

	left := titleStyle.Render(" Coal ")
	right := dimStyle.Render(fmt.Sprintf("%s · %s ",
		orDash(m.modelName), "chipflow"))
	gap := w - lipgloss.Width(left) - lipgloss.Width(right)
	if gap < 1 {
		gap = 1
	}
	header := left + strings.Repeat(" ", gap) + right
	divider := dimStyle.Render(strings.Repeat("─", w))

	status := " " + m.status
	if m.busy {
		spin := []string{"⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"}
		idx := int(time.Since(m.started).Milliseconds()/120) % len(spin)
		status = " " + spin[idx] + " " + m.status
	}
	rightStatus := ""
	if m.busy {
		rightStatus = fmt.Sprintf("%.1fs ", time.Since(m.started).Seconds())
	} else if m.lastMS > 0 {
		rightStatus = fmt.Sprintf("%.1fs ", float64(m.lastMS)/1000)
	}
	gap2 := w - lipgloss.Width(status) - lipgloss.Width(rightStatus) - 1
	if gap2 < 0 {
		gap2 = 0
	}
	statusLine := statusStyle.Render(status) +
		strings.Repeat(" ", gap2) + statusStyle.Render(rightStatus)

	input := boxStyle.Width(w - 2).Render(m.input.View())
	hint := dimStyle.Render(" enter send · ctrl+c interrupt/quit · " +
		"pgup/pgdn scroll · ctrl+d quit")

	rowsOut := []string{header, divider}
	if m.banner != "" {
		rowsOut = append(rowsOut, errStyle.Render(" "+m.banner))
	}
	rowsOut = append(rowsOut, m.vp.View(), statusLine, input, hint,
		dimStyle.Render(" ctrl+t thinking · ctrl+o tool output · "+
			"ctrl+w wsl install"))
	return strings.Join(rowsOut, "\n")
}

func (m model) bannerLines() int {
	if m.banner != "" {
		return 1
	}
	return 0
}

func orDash(s string) string {
	if s == "" {
		return "local"
	}
	return s
}

// ---------------------------------------------------------------- main
func selftest(roxChat string) {
	m := newModel(roxChat)
	deadline := time.After(90 * time.Second)
	sent := false
	fmt.Println("selftest: child started in", roxChat)
	for {
		select {
		case e := <-m.ch:
			fmt.Printf("event: %-8s %s\n", e.T, trunc(e.Name, 60))
			if e.T == "ready" && !sent {
				sent = true
				b, _ := json.Marshal(map[string]string{
					"prompt": "Reply with exactly: ok"})
				m.stdin.Write(append(b, '\n'))
				fmt.Println("sent prompt")
			}
			if e.T == "error" {
				fmt.Println("error:", e.Message)
				return
			}
			if e.T == "done" {
				fmt.Println("selftest: OK")
				return
			}
		case <-deadline:
			fmt.Println("selftest: TIMEOUT")
			return
		}
	}
}

func main() {
	dir := flag.String("dir", "", "path to coal_chat (default: parent of exe)")
	selft := flag.Bool("selftest", false, "run one prompt headlessly and exit")
	flag.Parse()

	roxChat := *dir
	if roxChat == "" {
		if exe, err := os.Executable(); err == nil {
			roxChat = filepath.Clean(filepath.Join(filepath.Dir(exe), ".."))
		} else {
			roxChat = "."
		}
	}
	if *selft {
		selftest(roxChat)
		return
	}

	p := tea.NewProgram(newModel(roxChat), tea.WithAltScreen())
	if _, err := p.Run(); err != nil {
		fmt.Fprintln(os.Stderr, "coal-tui:", err)
		os.Exit(1)
	}
}
