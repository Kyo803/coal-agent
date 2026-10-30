package main

import (
	"bufio"
	"encoding/json"
	"fmt"
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

// ---------------------------------------------------------------- config

func coalDir() string {
	if d := os.Getenv("COAL_HOME"); d != "" {
		return d
	}
	return `C:\Users\gamel\OneDrive\Documents\Default Project\Coal\lm_track\coal_chat`
}

func pythonExe() string {
	if p := os.Getenv("COAL_PY"); p != "" {
		return p
	}
	cand := `C:\Users\gamel\AppData\Local\Python\pythoncore-3.15-64\python.exe`
	if _, err := os.Stat(cand); err == nil {
		return cand
	}
	return "py"
}

// ---------------------------------------------------------------- events

type Event struct {
	T       string         `json:"t"`
	Text    string         `json:"text"`
	Name    string         `json:"name"`
	Args    map[string]any `json:"args"`
	Output  string         `json:"output"`
	Model   string         `json:"model"`
	Message string         `json:"message"`
	MS      int            `json:"ms"`
	Kind    string         `json:"kind"`
}

type evMsg Event
type doneMsg struct{ err error }
type tickMsg time.Time

var program *tea.Program

// ---------------------------------------------------------------- styles

var (
	purple  = lipgloss.Color("141")
	dim     = lipgloss.Color("240")
	green   = lipgloss.Color("78")
	red     = lipgloss.Color("203")
	cyan    = lipgloss.Color("80")
	titleSt = lipgloss.NewStyle().Bold(true).Foreground(purple)
	dimSt   = lipgloss.NewStyle().Foreground(dim)
	errSt   = lipgloss.NewStyle().Foreground(red)
	toolSt  = lipgloss.NewStyle().Foreground(cyan)
	youSt   = lipgloss.NewStyle().Bold(true).Foreground(green)
	thinkSt = lipgloss.NewStyle().Foreground(dim).Italic(true)
)

// ---------------------------------------------------------------- model

type model struct {
	input    textinput.Model
	vp       viewport.Model
	ready    bool
	width    int
	height   int
	history  []string
	thinking strings.Builder
	answer   strings.Builder
	running  bool
	started  time.Time
	elapsed  time.Duration
	modelID  string
	tools    int
	spin     int
	err      error
}

func initialModel() model {
	ti := textinput.New()
	ti.Placeholder = "Ask Coal…  (Enter to send, Ctrl+C to quit)"
	ti.CharLimit = 8000
	ti.Width = 80
	ti.Focus()
	ti.Prompt = "› "
	return model{input: ti}
}

func (m model) Init() tea.Cmd { return textinput.Blink }

func tick() tea.Cmd {
	return tea.Tick(100*time.Millisecond, func(t time.Time) tea.Msg {
		return tickMsg(t)
	})
}

// ---------------------------------------------------------------- run Coal

func runCoal(prompt string, p *tea.Program) {
	cmd := exec.Command(pythonExe(), "coal.py", "--json-events",
		"--no-autostart", "--say", prompt)
	cmd.Dir = coalDir()
	cmd.Env = append(os.Environ(),
		"CoalO_35B=1", "PYTHONIOENCODING=utf-8", "PYTHONUTF8=1")

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		p.Send(doneMsg{err})
		return
	}
	cmd.Stderr = nil
	if err := cmd.Start(); err != nil {
		p.Send(doneMsg{err})
		return
	}
	sc := bufio.NewScanner(stdout)
	sc.Buffer(make([]byte, 1024*1024), 8*1024*1024)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || !strings.HasPrefix(line, "{") {
			continue
		}
		var ev Event
		if json.Unmarshal([]byte(line), &ev) == nil {
			p.Send(evMsg(ev))
		}
	}
	err = cmd.Wait()
	p.Send(doneMsg{err})
}

// ---------------------------------------------------------------- update

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmds []tea.Cmd
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width, m.height = msg.Width, msg.Height
		h := msg.Height - 9
		if h < 3 {
			h = 3
		}
		if !m.ready {
			m.vp = viewport.New(msg.Width, h)
			m.ready = true
		} else {
			m.vp.Width = msg.Width
			m.vp.Height = h
		}
		m.input.Width = msg.Width - 4
		m.refreshViewport()

	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c", "esc":
			return m, tea.Quit
		case "enter":
			if m.running {
				return m, nil
			}
			prompt := strings.TrimSpace(m.input.Value())
			if prompt == "" {
				return m, nil
			}
			m.input.SetValue("")
			m.history = append(m.history, youSt.Render("you › ")+prompt, "")
			m.running = true
			m.started = time.Now()
			m.elapsed = 0
			m.tools = 0
			m.err = nil
			m.thinking.Reset()
			m.answer.Reset()
			m.refreshViewport()
			m.vp.GotoBottom()
			return m, func() tea.Msg {
				go runCoal(prompt, program)
				return tick()
			}
		}

	case evMsg:
		ev := Event(msg)
		switch ev.T {
		case "start":
			m.modelID = ev.Model
		case "thinking":
			m.thinking.WriteString(ev.Text)
		case "token":
			m.answer.WriteString(ev.Text)
		case "tool":
			m.tools++
			args := ""
			if len(ev.Args) > 0 {
				b, _ := json.Marshal(ev.Args)
				args = string(b)
				if len(args) > 90 {
					args = args[:90] + "…"
				}
			}
			line := toolSt.Render("⚙ "+ev.Name) + dimSt.Render(" "+args)
			m.history = append(m.history, line)
			m.refreshViewport()
			m.vp.GotoBottom()
		case "answer":
			if ev.Text != "" {
				m.answer.Reset()
				m.answer.WriteString(ev.Text)
			}
		case "error":
			m.err = fmt.Errorf("%s", ev.Message)
		}

	case doneMsg:
		m.running = false
		if m.answer.Len() > 0 {
			m.history = append(m.history, m.answer.String(), "")
		}
		if m.err != nil {
			m.history = append(m.history, errSt.Render("error: "+m.err.Error()), "")
		}
		m.thinking.Reset()
		m.answer.Reset()
		if msg.err != nil && !strings.Contains(msg.err.Error(), "exit status 0") {
			// process-level failure
			m.history = append(m.history,
				dimSt.Render("process: "+msg.err.Error()), "")
		}
		m.refreshViewport()
		m.vp.GotoBottom()
		return m, nil

	case tickMsg:
		if m.running {
			m.elapsed = time.Since(m.started)
			m.spin = (m.spin + 1) % 10
			return m, tick()
		}
	}

	var cmd tea.Cmd
	m.input, cmd = m.input.Update(msg)
	cmds = append(cmds, cmd)
	if m.ready {
		m.vp, cmd = m.vp.Update(msg)
		cmds = append(cmds, cmd)
	}
	return m, tea.Batch(cmds...)
}

func (m *model) refreshViewport() {
	if !m.ready {
		return
	}
	m.vp.SetContent(strings.Join(m.history, "\n"))
}

// ---------------------------------------------------------------- view

var frames = []string{"⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"}

func (m model) View() string {
	if !m.ready {
		return "starting…"
	}
	var b strings.Builder

	modelName := m.modelID
	if modelName == "" {
		modelName = "Coal"
	}
	status := "idle"
	if m.running {
		status = "thinking"
	}
	header := titleSt.Render(" Coal ") +
		dimSt.Render(" "+modelName+"  ·  "+status)
	b.WriteString(header + "\n")
	b.WriteString(dimSt.Render(strings.Repeat("─", max(10, m.width))) + "\n")

	b.WriteString(m.vp.View())
	b.WriteString("\n")

	// live area
	if m.running {
		el := fmt.Sprintf("%.1fs", m.elapsed.Seconds())
		b.WriteString(thinkSt.Render(frames[m.spin] + " thinking " + el +
			"  ·  tools " + fmt.Sprint(m.tools)))
		if m.thinking.Len() > 0 {
			b.WriteString("\n")
			b.WriteString(thinkSt.Render(truncate(m.thinking.String(), 6, m.width)))
		}
		if m.answer.Len() > 0 {
			b.WriteString("\n")
			b.WriteString(m.answer.String())
		}
		b.WriteString("\n")
	}

	b.WriteString(m.input.View() + "\n")
	footer := dimSt.Render(" enter send · ctrl+c quit · small local model")
	b.WriteString(footer)
	return b.String()
}

func truncate(s string, maxLines, width int) string {
	lines := strings.Split(strings.TrimRight(s, " \n"), "\n")
	if len(lines) > maxLines {
		lines = lines[len(lines)-maxLines:]
	}
	out := make([]string, 0, len(lines))
	for _, ln := range lines {
		if len(ln) > width-4 && width > 8 {
			ln = ln[:width-4] + "…"
		}
		out = append(out, "  "+ln)
	}
	return strings.Join(out, "\n")
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

// ---------------------------------------------------------------- main

// runOnce is a non-interactive smoke test / scripting mode:
//   coal-tui.exe --once "your prompt"
func runOnce(prompt string) {
	cmd := exec.Command(pythonExe(), "coal.py", "--json-events",
		"--no-autostart", "--say", prompt)
	cmd.Dir = coalDir()
	cmd.Env = append(os.Environ(),
		"CoalO_35B=1", "PYTHONIOENCODING=utf-8", "PYTHONUTF8=1")
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		fmt.Println("error:", err)
		return
	}
	if err := cmd.Start(); err != nil {
		fmt.Println("error:", err)
		return
	}
	start := time.Now()
	var think strings.Builder
	sc := bufio.NewScanner(stdout)
	sc.Buffer(make([]byte, 1024*1024), 8*1024*1024)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || !strings.HasPrefix(line, "{") {
			continue
		}
		var ev Event
		if json.Unmarshal([]byte(line), &ev) != nil {
			continue
		}
		switch ev.T {
		case "start":
			fmt.Printf("model: %s\n", ev.Model)
		case "thinking":
			think.WriteString(ev.Text)
		case "tool":
			b, _ := json.Marshal(ev.Args)
			fmt.Printf("  tool %s %s\n", ev.Name, string(b))
		case "token":
			fmt.Print(ev.Text)
		case "answer":
			fmt.Println()
		case "done":
			if think.Len() > 0 {
				fmt.Printf("\n[thinking %.1fs]\n%s\n",
					time.Since(start).Seconds(),
					truncate(think.String(), 6, 100))
			}
			fmt.Printf("\n[done in %d ms · kind=%s]\n", ev.MS, ev.Kind)
		case "error":
			fmt.Println("\nerror:", ev.Message)
		}
	}
	_ = cmd.Wait()
}

func main() {
	_ = filepath.Clean(coalDir())
	if len(os.Args) >= 3 && os.Args[1] == "--once" {
		runOnce(strings.Join(os.Args[2:], " "))
		return
	}
	program = tea.NewProgram(initialModel(), tea.WithAltScreen())
	if _, err := program.Run(); err != nil {
		fmt.Println("coal tui error:", err)
	}
}
