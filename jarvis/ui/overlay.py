"""
jarvis/ui/overlay.py
====================
Floating HUD overlay with a high-tech animated Arc Reactor.

States:
  idle       – slow breathing cyan core glow, slow rotation of tech arcs
  listening  – rapid white/cyan core pulse, expanding ripple rings
  thinking   – orbiting purple dots, rapid counter-rotation of arcs
  speaking   – core scaling/pulsing in sync with voice/text, green ripple waves
  sleeping   – dimmed grey-blue core, static arcs, floating Z particles

Thread-safe: all public methods enqueue work on the Tkinter thread.
"""

import tkinter as tk
import threading
import math
import queue
import logging
import time


class JarvisOverlay:
    # ── State constants ──────────────────────────────────────────────────
    STATE_IDLE      = "idle"
    STATE_LISTENING = "listening"
    STATE_THINKING  = "thinking"
    STATE_SPEAKING  = "speaking"
    STATE_SLEEPING  = "sleeping"

    # ── Palette ──────────────────────────────────────────────────────────
    C = {
        "bg":             "#060a14",
        "panel":          "#0b1221",
        "panel2":         "#0f1a2e",
        "border":         "#1c3a5e",
        "border_bright":  "#2a5a8e",
        "head_fill":      "#0e1830",
        "head_outline":   "#1e3a5e",
        "eye_on":         "#00d4ff",
        "eye_off":        "#0a1e30",
        "eye_glow":       "#60e8ff",
        "glow_blue":      "#00c8f0",
        "glow_purple":    "#7c3aed",
        "glow_green":     "#22c55e",
        "mouth_on":       "#00d4ff",
        "mouth_off":      "#0a2a40",
        "ant_idle":       "#0d2a40",
        "ant_active":     "#00d4ff",
        "text":           "#c8e8ff",
        "text_dim":       "#2e5570",
        "text_accent":    "#60b8e0",
        "z_col":          "#1a4060",
        "name_col":       "#4da8d8",
        "status_idle":    "#2e5570",
        "status_listen":  "#00c8f0",
        "status_think":   "#9b6fff",
        "status_speak":   "#22c55e",
        "status_sleep":   "#152030",
    }

    HUD_W    = 240
    HUD_H    = 580
    CHAR_CX  = 120   # character canvas center X
    CHAR_CY  = 105   # character canvas center Y
    CANVAS_H = 210

    SLEEP_TIMEOUT_MS = 60_000   # 1 minute

    # ── Init ─────────────────────────────────────────────────────────────
    def __init__(self):
        self.logger = logging.getLogger("Jarvis.Overlay")
        self._queue: queue.Queue = queue.Queue()
        self._state   = self.STATE_IDLE
        self._running = True
        self._tick    = 0
        self._reactor_angle = 0
        self._start_time = time.time()
        self._command_cb = None

        # Typewriter state
        self._tw_words  = []
        self._tw_index  = 0
        self._tw_job    = None

        # Sleep timer job
        self._sleep_job = None

        # Z-particle list: [{x, y, age, letter}]
        self._z_particles = []

        # Drag state (full HUD)
        self._drag_ox = 0
        self._drag_oy = 0

        # Minimize-to-bubble state
        self._minimized   = False
        self._bubble_win  = None
        self._bubble_cv   = None
        self._bubble_ox   = 0
        self._bubble_oy   = 0

        # Canvas item handles
        self._item_reactor_arc1 = None
        self._item_reactor_arc2 = None
        self._item_core_glow    = None
        self._item_core         = None

        # Telemetry state
        self._val_bangalore_weather = "Fetching..."
        self._val_cpu_temp = "Fetching..."
        self._val_cpu_usage = "Fetching..."
        self._val_gpu_usage = "Fetching..."

        self._telemetry_thread = threading.Thread(
            target=self._run_telemetry, daemon=True, name="TelemetryWorker")
        self._telemetry_thread.start()

        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run_ui, daemon=True, name="JarvisHUD")
        self._thread.start()
        self._ready.wait(timeout=6)
        self.logger.info("JarvisOverlay started.")

    # ── Public thread-safe API ────────────────────────────────────────────

    def set_command_callback(self, cb):
        """Register the command handler callback."""
        self._command_cb = cb

    def get_entry_text(self) -> str:
        """Thread-safe way to retrieve text currently entered in the entry box."""
        res_q = queue.Queue()
        def _get():
            val = ""
            if hasattr(self, "_entry_cmd") and self._entry_cmd:
                val = self._entry_cmd.get().strip()
                if val == "Type a command...":
                    val = ""
            res_q.put(val)
        self.root.after(0, _get)
        try:
            return res_q.get(timeout=1.0)
        except Exception:
            return ""

    def clear_entry_text(self):
        """Thread-safe clear entry text."""
        def _clear():
            if hasattr(self, "_entry_cmd") and self._entry_cmd:
                self._entry_cmd.delete(0, "end")
                self._entry_cmd.insert(0, "Type a command...")
                self._entry_cmd.config(fg=self.C["text_dim"])
        self.root.after(0, _clear)

    def show_text(self, text: str):
        """Display Jarvis response word-by-word in the HUD (from any thread)."""
        self._queue.put(("show_text", text))

    def show_live_text(self, partial: str):
        """Show live partial transcription of user speech (from any thread)."""
        self._queue.put(("live_text", partial))

    def clear_live_text(self):
        """Clear the live transcription display (from any thread)."""
        self._queue.put(("live_text", ""))

    def set_state(self, state: str):
        """Change character animation state (from any thread)."""
        self._queue.put(("set_state", state))

    def reset_sleep_timer(self):
        """Reset the 1-minute sleep countdown (from any thread)."""
        self._queue.put(("reset_sleep", None))

    def wake_from_sleep(self):
        """Force wake from sleep (from any thread)."""
        self._queue.put(("wake", None))

    def destroy_safe(self):
        """Gracefully close the HUD window (from any thread)."""
        self._running = False
        self._queue.put(("destroy", None))

    # ── UI thread entry point ─────────────────────────────────────────────

    def _run_ui(self):
        try:
            self.root = tk.Tk()
            self._setup_window()
            self._build_ui()
            self._ready.set()
            self._process_queue()
            self._animate()
            self._arm_sleep_timer()
            self._update_clock_widgets()
            self.root.mainloop()
        except Exception as exc:
            self.logger.error(f"Overlay thread error: {exc}", exc_info=True)
            self._ready.set()

    def _setup_window(self):
        r = self.root
        r.title("Jarvis")
        r.overrideredirect(True)           # No OS window chrome
        r.wm_attributes("-topmost", True)  # Always on top
        r.wm_attributes("-alpha", 0.93)    # Slight transparency
        r.configure(bg=self.C["bg"])
        r.resizable(False, False)

        sw = r.winfo_screenwidth()
        sh = r.winfo_screenheight()
        x = sw - self.HUD_W - 18
        y = (sh - self.HUD_H) // 2
        r.geometry(f"{self.HUD_W}x{self.HUD_H}+{x}+{y}")

        # Drag bindings
        r.bind("<ButtonPress-1>",   self._on_drag_start)
        r.bind("<B1-Motion>",       self._on_drag_motion)

    # ── Widget construction ───────────────────────────────────────────────

    def _build_ui(self):
        C = self.C
        r = self.root

        # ─ Outer border ring ─
        outer = tk.Frame(r, bg=C["border"], padx=1, pady=1)
        outer.pack(fill="both", expand=True)

        inner = tk.Frame(outer, bg=C["panel"])
        inner.pack(fill="both", expand=True)

        # ─ Top header bar ─
        hdr = tk.Frame(inner, bg=C["panel2"], height=32)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        btn_jarvis = tk.Label(
            hdr, text=" ◈ JARVIS",
            font=("Consolas", 9, "bold"),
            fg=C["name_col"], bg=C["panel2"],
            cursor="hand2")
        btn_jarvis.pack(side="left", pady=6, padx=(6, 0))

        def _on_minimize_click(e):
            self._toggle_minimize()
            return "break"

        btn_jarvis.bind("<ButtonRelease-1>", _on_minimize_click)
        btn_jarvis.bind("<ButtonPress-1>",   lambda e: "break")

        # Spacer to keep status on the right and JARVIS on the left
        tk.Label(hdr, bg=C["panel2"]).pack(side="left", expand=True)

        self._lbl_status = tk.Label(
            hdr, text="● STANDING BY",
            font=("Consolas", 7, "bold"),
            fg=C["status_idle"], bg=C["panel2"])
        self._lbl_status.pack(side="right", padx=6, pady=6)

        # ─ Character canvas ─
        tk.Frame(inner, height=1, bg=C["border"]).pack(fill="x")
        self._canvas = tk.Canvas(
            inner,
            width=self.HUD_W - 2,
            height=self.CANVAS_H,
            bg=C["panel"], highlightthickness=0)
        self._canvas.pack()

        self._draw_character_static()

        # ─ Divider ─
        tk.Frame(inner, height=1, bg=C["border"]).pack(fill="x")

        # ─ Text input area ─
        input_frame = tk.Frame(inner, bg=C["panel"])
        input_frame.pack(fill="x", padx=12, pady=6)

        self._entry_cmd = tk.Entry(
            input_frame,
            font=("Segoe UI", 9),
            bg=C["panel2"],
            fg=C["text"],
            insertbackground=C["eye_on"],
            bd=1,
            relief="flat",
            highlightthickness=1,
            highlightbackground=C["border"],
            highlightcolor=C["border_bright"]
        )
        self._entry_cmd.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._entry_cmd.insert(0, "Type a command...")
        self._entry_cmd.config(fg=C["text_dim"])

        def on_focus_in(event):
            if self._entry_cmd.get() == "Type a command...":
                self._entry_cmd.delete(0, "end")
                self._entry_cmd.config(fg=C["text"])

        def on_focus_out(event):
            if not self._entry_cmd.get():
                self._entry_cmd.insert(0, "Type a command...")
                self._entry_cmd.config(fg=C["text_dim"])

        self._entry_cmd.bind("<FocusIn>", on_focus_in)
        self._entry_cmd.bind("<FocusOut>", on_focus_out)

        btn_send = tk.Button(
            input_frame,
            text="SEND",
            font=("Consolas", 8, "bold"),
            bg=C["border"],
            fg=C["text"],
            activebackground=C["border_bright"],
            activeforeground=C["text"],
            relief="flat",
            bd=0,
            command=self._on_send_click,
            cursor="hand2"
        )
        btn_send.pack(side="right", padx=2, pady=1)
        self._entry_cmd.bind("<Return>", lambda e: self._on_send_click())

        # ─ Divider ─
        tk.Frame(inner, height=1, bg=C["border"]).pack(fill="x", padx=6)

        # ─ Live user speech label ("You:") ─
        live_hdr = tk.Frame(inner, bg=C["panel"])
        live_hdr.pack(fill="x", padx=12, pady=(4, 0))
        tk.Label(live_hdr, text="YOU",
                 font=("Consolas", 6, "bold"),
                 fg=C["text_dim"], bg=C["panel"]).pack(side="left")

        self._var_live = tk.StringVar(value="")
        self._lbl_live = tk.Label(
            inner,
            textvariable=self._var_live,
            font=("Segoe UI", 8, "italic"),
            fg=C["status_listen"],   # cyan
            bg=C["panel"],
            wraplength=self.HUD_W - 20,
            justify="left",
            anchor="nw",
            height=2,
        )
        self._lbl_live.pack(fill="x", padx=12, pady=(0, 2))

        # ─ Divider ─
        tk.Frame(inner, height=1, bg=C["border"]).pack(fill="x", padx=6)

        # ─ Jarvis response label ─
        resp_hdr = tk.Frame(inner, bg=C["panel"])
        resp_hdr.pack(fill="x", padx=12, pady=(4, 0))
        tk.Label(resp_hdr, text="JARVIS",
                 font=("Consolas", 6, "bold"),
                 fg=C["text_dim"], bg=C["panel"]).pack(side="left")

        # ─ Text display ─
        self._txt_resp = tk.Text(
            inner,
            font=("Segoe UI", 9),
            fg=C["text"],
            bg=C["panel"],
            bd=0, relief="flat",
            highlightthickness=0,
            wrap="word",
            height=4,
            state="disabled",
            cursor="arrow",
        )
        self._txt_resp.pack(fill="x", padx=12, pady=(0, 4))
        self._txt_resp.tag_configure("jarvis",
                                      font=("Segoe UI", 9),
                                      foreground=C["text"])

        # ─ Divider ─
        tk.Frame(inner, height=1, bg=C["border"]).pack(fill="x", padx=6)

        # ── Grid of widgets at the bottom ──
        grid_frame = tk.Frame(inner, bg=C["panel"])
        grid_frame.pack(fill="x", padx=10, pady=(4, 8))
        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=1)

        self._lbl_weather_val = self._create_widget_box(grid_frame, 0, 0, "BANGALORE TEMP", "Fetching...")
        self._lbl_cputemp_val = self._create_widget_box(grid_frame, 0, 1, "CPU TEMP", "Fetching...")
        self._lbl_cpuusage_val = self._create_widget_box(grid_frame, 1, 0, "CPU USAGE", "Fetching...")
        self._lbl_gpuusage_val = self._create_widget_box(grid_frame, 1, 1, "GPU USAGE", "Fetching...")

    def _create_widget_box(self, parent, row, col, title, value_str):
        C = self.C
        box = tk.Frame(parent, bg=C["panel2"], bd=1, relief="flat", highlightthickness=1, highlightbackground=C["border"])
        box.grid(row=row, column=col, padx=3, pady=3, sticky="nsew")
        
        lbl_title = tk.Label(box, text=title, font=("Consolas", 6, "bold"), fg=C["text_dim"], bg=C["panel2"])
        lbl_title.pack(anchor="w", padx=6, pady=(3, 0))
        
        lbl_val = tk.Label(box, text=value_str, font=("Consolas", 9, "bold"), fg=C["eye_on"], bg=C["panel2"])
        lbl_val.pack(anchor="w", padx=6, pady=(0, 3))
        return lbl_val

    def _on_send_click(self):
        cmd = self._entry_cmd.get().strip()
        if not cmd or cmd == "Type a command...":
            return
        
        # Reset Entry
        self._entry_cmd.delete(0, "end")
        self._entry_cmd.insert(0, "Type a command...")
        self._entry_cmd.config(fg=self.C["text_dim"])
        
        self.root.focus_set()

        if hasattr(self, "_command_cb") and self._command_cb:
            threading.Thread(target=self._command_cb, args=(cmd,), daemon=True).start()

    # ── Character drawing ─────────────────────────────────────────────────

    def _draw_character_static(self):
        cv  = self._canvas
        C   = self.C
        cx, cy = self.CHAR_CX, self.CHAR_CY

        # Outer tech ring/halo
        for r, col in [
            (75, "#020813"), (68, "#041024"), (60, "#061836"), (52, "#082046")
        ]:
            cv.create_oval(cx-r, cy-r, cx+r, cy+r,
                           fill="", outline=col, width=1.5, tags="glow_halo")

        # Rotating outer tech arcs
        self._item_reactor_arc1 = cv.create_arc(
            cx-48, cy-48, cx+48, cy+48,
            start=0, extent=120,
            style=tk.ARC, outline=C["eye_on"], width=2.5,
            tags="reactor_arc1")
        self._item_reactor_arc2 = cv.create_arc(
            cx-48, cy-48, cx+48, cy+48,
            start=180, extent=120,
            style=tk.ARC, outline=C["eye_on"], width=2.5,
            tags="reactor_arc2")

        # Inner segmented detailed tech ring
        cv.create_oval(cx-36, cy-36, cx+36, cy+36,
                       fill="", outline="#112b4d", width=1.5, dash=(6, 4), tags="reactor_ring_dash")

        # Core backing glow
        self._item_core_glow = cv.create_oval(
            cx-24, cy-24, cx+24, cy+24,
            fill="#092844", outline="#1c4876", width=2,
            tags="core_glow")

        # Arc Reactor Center Core (White glowing circle)
        self._item_core = cv.create_oval(
            cx-15, cy-15, cx+15, cy+15,
            fill="#ffffff", outline=C["eye_on"], width=2.5,
            tags="reactor_core")

    # ── Master animation loop ─────────────────────────────────────────────

    def _animate(self):
        if not self._running:
            return
        self._tick += 1
        t = self._tick
        try:
            s = self._state
            if   s == self.STATE_SLEEPING:  self._anim_sleep(t)
            elif s == self.STATE_SPEAKING:  self._anim_speaking(t)
            elif s == self.STATE_LISTENING: self._anim_listening(t)
            elif s == self.STATE_THINKING:  self._anim_thinking(t)
            else:                           self._anim_idle(t)
        except Exception:
            pass
        self.root.after(33, self._animate)  # ~30 fps

    # ── State animations ──────────────────────────────────────────────────

    def _anim_idle(self, t):
        C  = self.C
        cv = self._canvas
        cx, cy = self.CHAR_CX, self.CHAR_CY

        # Slow rotation of arcs
        self._reactor_angle = (self._reactor_angle + 1) % 360
        cv.itemconfig(self._item_reactor_arc1, start=self._reactor_angle, outline=C["eye_on"])
        cv.itemconfig(self._item_reactor_arc2, start=(self._reactor_angle + 180) % 360, outline=C["eye_on"])

        # Slow breathing core glow (0.25 Hz)
        pulse = 0.5 + 0.5 * math.sin(t * 0.05)
        glow_col = self._lerp("#092844", "#123f66", pulse)
        cv.itemconfig(self._item_core_glow, fill=glow_col)
        cv.itemconfig(self._item_core, fill="#ffffff", outline=C["eye_on"])
        cv.coords(self._item_core, cx-15, cy-15, cx+15, cy+15)

        cv.delete("listen_arc", "think_dot", "speak_wave", "z_particle")

        self._lbl_status.config(text="● STANDING BY", fg=C["status_idle"])

    def _anim_listening(self, t):
        C  = self.C
        cv = self._canvas
        cx, cy = self.CHAR_CX, self.CHAR_CY

        # Slow rotation of arcs
        self._reactor_angle = (self._reactor_angle + 1) % 360
        cv.itemconfig(self._item_reactor_arc1, start=self._reactor_angle, outline=C["eye_glow"])
        cv.itemconfig(self._item_reactor_arc2, start=(self._reactor_angle + 180) % 360, outline=C["eye_glow"])

        # Rapid pulse of core
        pulse = 0.5 + 0.5 * math.sin(t * 0.25)
        core_col = self._lerp(C["eye_on"], "#ffffff", pulse)
        cv.itemconfig(self._item_core, fill=core_col, outline=C["eye_glow"])
        cv.itemconfig(self._item_core_glow, fill="#0c355a")
        cv.coords(self._item_core, cx-15, cy-15, cx+15, cy+15)

        # Ripple arcs
        cv.delete("listen_arc")
        phase = t % 25
        for i in range(1, 4):
            age = (phase + i * 8) % 25
            r   = 25 + age * 2.5
            alp = max(0.0, 0.7 - age * 0.028)
            col = self._alpha(C["glow_blue"], alp)
            cv.create_oval(cx-r, cy-r, cx+r, cy+r,
                           outline=col, width=1.5, tags="listen_arc")

        cv.delete("think_dot", "speak_wave", "z_particle")

        self._lbl_status.config(text="◉ LISTENING", fg=C["status_listen"])

    def _anim_thinking(self, t):
        C  = self.C
        cv = self._canvas
        cx, cy = self.CHAR_CX, self.CHAR_CY

        # Arcs rotate faster in opposite directions
        self._reactor_angle = (self._reactor_angle + 5) % 360
        cv.itemconfig(self._item_reactor_arc1, start=self._reactor_angle, outline=C["glow_purple"])
        cv.itemconfig(self._item_reactor_arc2, start=(360 - self._reactor_angle) % 360, outline=C["glow_purple"])

        # Core shifts to purple
        cv.itemconfig(self._item_core, fill="#ffffff", outline=C["glow_purple"])
        cv.itemconfig(self._item_core_glow, fill="#1c0c3a")
        cv.coords(self._item_core, cx-15, cy-15, cx+15, cy+15)

        # Orbiting dots
        cv.delete("think_dot")
        for i in range(5):
            angle = (t * 0.08 * math.pi) + (i * 2 * math.pi / 5)
            dx = 55 * math.cos(angle)
            dy = 55 * math.sin(angle)
            col = C["glow_purple"]
            cv.create_oval(cx+dx-3, cy+dy-3, cx+dx+3, cy+dy+3,
                           fill=col, outline="", tags="think_dot")

        cv.delete("listen_arc", "speak_wave", "z_particle")

        self._lbl_status.config(text="◈ THINKING", fg=C["status_think"])

    def _anim_speaking(self, t):
        C  = self.C
        cv = self._canvas
        cx, cy = self.CHAR_CX, self.CHAR_CY

        # Arcs spin
        self._reactor_angle = (self._reactor_angle + 3) % 360
        cv.itemconfig(self._item_reactor_arc1, start=self._reactor_angle, outline=C["glow_green"])
        cv.itemconfig(self._item_reactor_arc2, start=(self._reactor_angle + 180) % 360, outline=C["glow_green"])

        # Core scale / size pulse
        scale = 14 + 4 * abs(math.sin(t * 0.3))
        cv.coords(self._item_core, cx-scale, cy-scale, cx+scale, cy+scale)
        cv.itemconfig(self._item_core, fill=C["glow_green"], outline="#ffffff")
        cv.itemconfig(self._item_core_glow, fill="#0c3c1a")

        # Sound wave rings from core
        cv.delete("speak_wave")
        phase = t % 18
        for i in range(2):
            age = (phase + i * 9) % 18
            r   = 25 + age * 2.0
            alp = max(0.0, 0.7 - age * 0.04)
            col = self._alpha(C["glow_green"], alp)
            cv.create_oval(cx-r, cy-r, cx+r, cy+r,
                           outline=col, width=1.5, tags="speak_wave")

        cv.delete("listen_arc", "think_dot", "z_particle")

        self._lbl_status.config(text="◉ SPEAKING", fg=C["status_speak"])

    def _anim_sleep(self, t):
        C  = self.C
        cv = self._canvas
        cx, cy = self.CHAR_CX, self.CHAR_CY

        # Dim static reactor
        cv.itemconfig(self._item_core, fill="#041020", outline="#0b223c")
        cv.itemconfig(self._item_core_glow, fill="#020812")
        cv.itemconfig(self._item_reactor_arc1, outline="#0b223c")
        cv.itemconfig(self._item_reactor_arc2, outline="#0b223c")
        cv.coords(self._item_core, cx-15, cy-15, cx+15, cy+15)

        # Floating Z particles
        cv.delete("z_particle")
        if t % 50 == 0 and len(self._z_particles) < 6:
            self._z_particles.append({
                "x": cx + 15,
                "y": float(cy - 15),
                "age": 0,
                "letter": "Z" if len(self._z_particles) % 2 == 0 else "z",
            })
        alive = []
        for p in self._z_particles:
            p["age"] += 1
            p["y"]   -= 0.6
            p["x"]   += math.sin(p["age"] * 0.1) * 0.4
            alp  = max(0.0, 1.0 - p["age"] / 80.0)
            size = max(6, 6 + int(p["age"] * 0.04))
            if alp > 0.05 and p["age"] < 80:
                col = self._alpha(C["z_col"], alp)
                cv.create_text(
                    p["x"], p["y"],
                    text=p["letter"],
                    font=("Consolas", size, "bold"),
                    fill=col, tags="z_particle")
                alive.append(p)
        self._z_particles = alive

        cv.delete("listen_arc", "think_dot", "speak_wave")

        self._lbl_status.config(text="◌ SLEEPING", fg=C["status_sleep"])

    # ── Queue processor ───────────────────────────────────────────────────

    def _process_queue(self):
        try:
            while True:
                cmd, data = self._queue.get_nowait()
                if cmd == "destroy":
                    try:
                        self.root.quit()
                    except Exception:
                        pass
                    return
                elif cmd == "show_text":
                    self._begin_typewriter(data)
                elif cmd == "live_text":
                    self._var_live.set(data)
                elif cmd == "set_state":
                    self._change_state(data)
                elif cmd == "reset_sleep":
                    self._restart_sleep_timer()
                elif cmd == "wake":
                    self._do_wake()
        except queue.Empty:
            pass
        if self._running:
            self.root.after(40, self._process_queue)

    # ── State management ──────────────────────────────────────────────────

    def _change_state(self, state: str):
        if self._state == self.STATE_SLEEPING and state != self.STATE_SLEEPING:
            self._do_wake()
        self._state = state

    def _do_wake(self):
        self._state = self.STATE_IDLE
        self._z_particles = []
        self._canvas.delete("z_particle")
        self._reset_head()
        self._restart_sleep_timer()

    def _reset_head(self):
        try:
            self._canvas.itemconfig(self._item_core_glow, fill="#092844")
            self._canvas.itemconfig(self._item_core, fill="#ffffff", outline=self.C["eye_on"])
        except Exception:
            pass

    # ── Sleep timer ───────────────────────────────────────────────────────

    def _arm_sleep_timer(self):
        self._cancel_sleep_timer()
        self._sleep_job = self.root.after(
            self.SLEEP_TIMEOUT_MS, self._go_to_sleep)

    def _restart_sleep_timer(self):
        self._cancel_sleep_timer()
        self._sleep_job = self.root.after(
            self.SLEEP_TIMEOUT_MS, self._go_to_sleep)

    def _cancel_sleep_timer(self):
        if self._sleep_job:
            try:
                self.root.after_cancel(self._sleep_job)
            except Exception:
                pass
            self._sleep_job = None

    def _go_to_sleep(self):
        self._state = self.STATE_SLEEPING
        self._z_particles = []
        try:
            self._txt_resp.config(state="normal")
            self._txt_resp.delete("1.0", "end")
            self._txt_resp.config(state="disabled")
        except Exception:
            pass

    # ── Typewriter ────────────────────────────────────────────────────────

    def _begin_typewriter(self, text: str):
        """Start displaying text word-by-word in the response Text widget."""
        if self._tw_job:
            try:
                self.root.after_cancel(self._tw_job)
            except Exception:
                pass
        self._tw_words  = text.split()
        self._tw_index  = 0
        self._tw_buffer = ""   # accumulated text so far
        # Clear display for new response
        self._txt_resp.config(state="normal")
        self._txt_resp.delete("1.0", "end")
        self._txt_resp.config(state="disabled")
        self._tick_typewriter()

    def _tick_typewriter(self):
        if self._tw_index < len(self._tw_words):
            word = self._tw_words[self._tw_index]
            sep  = "" if self._tw_index == 0 else " "
            self._tw_buffer += sep + word
            self._tw_index  += 1

            # Write into the Text widget
            self._txt_resp.config(state="normal")

            # Auto-clear when widget reaches 4 full lines of content
            line_count = int(self._txt_resp.index("end-1c").split(".")[0])
            if line_count > 4:
                self._txt_resp.delete("1.0", "end")
                self._tw_buffer = word

            self._txt_resp.insert("end", sep + word, "jarvis")
            self._txt_resp.see("end")   # scroll to latest word
            self._txt_resp.config(state="disabled")

            n_words = max(len(self._tw_words), 1)
            delay   = max(45, min(130, 650 // n_words))
            self._tw_job = self.root.after(delay, self._tick_typewriter)

    # ── Drag ──────────────────────────────────────────────────────────────

    def _on_drag_start(self, e):
        self._drag_ox = e.x
        self._drag_oy = e.y

    def _on_drag_motion(self, e):
        nx = self.root.winfo_x() + e.x - self._drag_ox
        ny = self.root.winfo_y() + e.y - self._drag_oy
        self.root.geometry(f"+{nx}+{ny}")

    # ── Minimize to bubble ────────────────────────────────────────────────

    def _toggle_minimize(self):
        if self._minimized:
            self._restore_from_bubble()
        else:
            self._minimize_to_bubble()

    def _minimize_to_bubble(self):
        """Hide full HUD, show a 70×70 draggable bubble with a mini Arc Reactor."""
        self._minimized = True
        self._hud_geom  = self.root.geometry()

        SZ = 70
        sw = self.root.winfo_screenwidth()

        bw = tk.Toplevel(self.root)
        bw.overrideredirect(True)
        bw.wm_attributes("-topmost", True)
        bw.wm_attributes("-alpha",   0.93)
        
        # Transparent key color for Windows to create perfect circular shape
        trans_color = "#000001"
        bw.configure(bg=trans_color)
        try:
            bw.wm_attributes("-transparentcolor", trans_color)
        except Exception:
            pass
            
        bw.geometry(f"{SZ}x{SZ}+{sw - SZ - 12}+{20}")

        bw.transient("")          # remove transient relationship
        bw.lift()                 # bring to front
        bw.update_idletasks()     # force render before root hides

        cv = tk.Canvas(bw, width=SZ, height=SZ,
                       bg=trans_color, highlightthickness=0)
        cv.pack(fill="both", expand=True)

        cx, cy = SZ // 2, SZ // 2

        # Outer glowing ring / window border
        cv.create_oval(2, 2, SZ-2, SZ-2,
                       outline=self.C["border_bright"], width=2,
                       fill=self.C["panel"])

        # Inner ring
        cv.create_oval(cx-18, cy-18, cx+18, cy+18,
                       outline=self.C["head_outline"], width=1, fill=self.C["head_fill"])

        # Mini Core
        self._bub_core = cv.create_oval(
            cx-7, cy-7, cx+7, cy+7,
            fill="#ffffff", outline=self.C["eye_on"], width=1.5)

        self._bubble_win = bw
        self._bubble_cv  = cv

        # Drag state: track start positions
        self._bub_ox = 0
        self._bub_oy = 0
        self._bub_press_x = 0
        self._bub_press_y = 0
        self._bub_moved   = False

        cv.bind("<ButtonPress-1>",   self._on_bubble_press)
        cv.bind("<B1-Motion>",       self._on_bubble_motion)
        cv.bind("<ButtonRelease-1>", self._on_bubble_release)

        self._bubble_animate()

        self.root.after(30, self.root.withdraw)

    def _bubble_animate(self):
        """Animate the mini Arc Reactor in the bubble."""
        if not self._minimized or not self._bubble_cv:
            return
        cv = self._bubble_cv
        t  = (self._tick % 60) / 60.0
        s  = self._state

        if s == self.STATE_IDLE:
            core_col = "#ffffff"
            core_outline = self._lerp(self.C["eye_on"], "#003850", 0.3 + 0.3 * abs(math.sin(t * math.pi)))
        elif s == self.STATE_LISTENING:
            core_col = self._lerp(self.C["eye_on"], "#ffffff", abs(math.sin(t * math.pi * 3)))
            core_outline = self.C["eye_glow"]
        elif s == self.STATE_THINKING:
            core_col = "#ffffff"
            core_outline = self.C["glow_purple"]
        elif s == self.STATE_SPEAKING:
            core_col = self.C["glow_green"]
            core_outline = "#ffffff"
        else:  # sleeping
            core_col = "#041020"
            core_outline = "#0b223c"

        try:
            cv.itemconfig(self._bub_core, fill=core_col, outline=core_outline)
        except Exception:
            pass

        if self._bubble_win:
            self._bubble_win.after(80, self._bubble_animate)

    def _restore_from_bubble(self):
        """Destroy bubble and restore the full HUD."""
        self._minimized = False
        if self._bubble_win:
            try:
                self._bubble_win.destroy()
            except Exception:
                pass
            self._bubble_win = None
            self._bubble_cv  = None
        self.root.deiconify()
        if hasattr(self, "_hud_geom") and self._hud_geom:
            self.root.geometry(self._hud_geom)
        self.root.lift()

    # ── Bubble drag handlers ──────────────────────────────────────────────

    def _on_bubble_press(self, e):
        self._bub_ox = e.x
        self._bub_oy = e.y
        self._bub_press_x = e.x_root
        self._bub_press_y = e.y_root
        self._bub_moved   = False

    def _on_bubble_motion(self, e):
        if (abs(e.x_root - self._bub_press_x) > 4 or
                abs(e.y_root - self._bub_press_y) > 4):
            self._bub_moved = True

        if self._bubble_win:
            nx = self._bubble_win.winfo_x() + e.x - self._bub_ox
            ny = self._bubble_win.winfo_y() + e.y - self._bub_oy
            self._bubble_win.geometry(f"+{nx}+{ny}")

    def _on_bubble_release(self, e):
        if not self._bub_moved:
            self._restore_from_bubble()

    # ── Clock / Timer Updater ─────────────────────────────────────────────

    def _update_clock_widgets(self):
        if not self._running:
            return
        try:
            if hasattr(self, "_lbl_weather_val") and self._lbl_weather_val:
                self._lbl_weather_val.config(text=self._val_bangalore_weather)
            if hasattr(self, "_lbl_cputemp_val") and self._lbl_cputemp_val:
                self._lbl_cputemp_val.config(text=self._val_cpu_temp)
            if hasattr(self, "_lbl_cpuusage_val") and self._lbl_cpuusage_val:
                self._lbl_cpuusage_val.config(text=self._val_cpu_usage)
            if hasattr(self, "_lbl_gpuusage_val") and self._lbl_gpuusage_val:
                self._lbl_gpuusage_val.config(text=self._val_gpu_usage)
        except Exception as e:
            self.logger.warning(f"Failed to update clock widgets: {e}")
            
        if self._running:
            self.root.after(1000, self._update_clock_widgets)

    def _run_telemetry(self):
        import urllib.request
        import json
        import subprocess
        
        has_psutil = False
        try:
            import psutil
            has_psutil = True
        except ImportError:
            pass
            
        weather_last_check = 0
        
        while self._running:
            # 1. Weather check (every 15 mins = 900s)
            now_time = time.time()
            if now_time - weather_last_check > 900:
                try:
                    url = "https://api.open-meteo.com/v1/forecast?latitude=12.9716&longitude=77.5946&current_weather=true"
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=5) as response:
                        w_data = json.loads(response.read().decode())
                        temp = w_data['current_weather']['temperature']
                        self._val_bangalore_weather = f"{temp}°C"
                        weather_last_check = now_time
                except Exception as e:
                    self.logger.debug(f"Failed to fetch weather: {e}")
                    # If failed, retry in 30 seconds
                    if weather_last_check == 0:
                        self._val_bangalore_weather = "Error"
                    weather_last_check = now_time - 870 
            
            # 2. CPU Usage
            if has_psutil:
                try:
                    self._val_cpu_usage = f"{psutil.cpu_percent(interval=None):.1f}%"
                except Exception:
                    self._val_cpu_usage = "Error"
            else:
                try:
                    cmd = 'typeperf "\\Processor(_Total)\\% Processor Time" -sc 1'
                    out = subprocess.check_output(cmd, shell=True, text=True)
                    lines = [line.strip() for line in out.splitlines() if line.strip()]
                    if len(lines) >= 3:
                        val = lines[2].split(",")[-1].replace('"', '')
                        self._val_cpu_usage = f"{float(val):.1f}%"
                except Exception:
                    self._val_cpu_usage = "Error"

            # 3. GPU Usage
            try:
                cmd = ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"]
                out = subprocess.check_output(cmd, text=True, timeout=2).strip()
                if out:
                    self._val_gpu_usage = f"{out}%"
            except Exception:
                self._val_gpu_usage = "N/A"

            # 4. CPU Temp
            temp_fetched = False
            # Try High Precision
            try:
                cmd = ["powershell", "-Command", "((Get-Counter -Counter '\\Thermal Zone Information(*)\\High Precision Temperature').CounterSamples).CookedValue"]
                out = subprocess.check_output(cmd, text=True, timeout=2).strip()
                if out:
                    vals = [float(v) for v in out.splitlines() if v.strip()]
                    if vals:
                        celsius = (max(vals) / 10.0) - 273.15
                        if 0 < celsius < 115:
                            self._val_cpu_temp = f"{celsius:.1f}°C"
                            temp_fetched = True
            except Exception:
                pass

            # Try standard temperature counter if high precision failed
            if not temp_fetched:
                try:
                    cmd = ["powershell", "-Command", "((Get-Counter -Counter '\\Thermal Zone Information(*)\\Temperature').CounterSamples).CookedValue"]
                    out = subprocess.check_output(cmd, text=True, timeout=2).strip()
                    if out:
                        vals = [float(v) for v in out.splitlines() if v.strip()]
                        if vals:
                            celsius = max(vals) - 273.15
                            if 0 < celsius < 115:
                                self._val_cpu_temp = f"{celsius:.1f}°C"
                                temp_fetched = True
                except Exception:
                    pass

            # Fallback to GPU temperature
            if not temp_fetched:
                try:
                    cmd = ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"]
                    out = subprocess.check_output(cmd, text=True, timeout=2).strip()
                    if out:
                        self._val_cpu_temp = f"{out}°C"
                        temp_fetched = True
                except Exception:
                    pass
                    
            if not temp_fetched:
                self._val_cpu_temp = "N/A"

            time.sleep(3)

    # ── Color helpers ─────────────────────────────────────────────────────

    def _lerp(self, c1: str, c2: str, t: float) -> str:
        """Linear interpolate between two #rrggbb hex colors."""
        t = max(0.0, min(1.0, t))
        r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
        r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
        return "#{:02x}{:02x}{:02x}".format(
            int(r1 + (r2-r1)*t),
            int(g1 + (g2-g1)*t),
            int(b1 + (b2-b1)*t))

    def _alpha(self, color: str, alpha: float) -> str:
        """Simulate alpha by blending with the panel background."""
        return self._lerp(self.C["panel"], color, alpha)
