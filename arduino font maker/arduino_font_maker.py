#!/usr/bin/env python3
"""
10x16 Arduino Font Editor (Tkinter)
Left-click/drag = draw, Right-click/drag = erase.
Shows all glyphs (ASCII 32–126) in a grid next to the editor.
Export produces an Arduino-compatible C header with uint8_t byte arrays
(row-major, MSB-first, 2 bytes per row = 20 bytes per glyph).

Reference font overlay: load any .txt font file as a ghost/template
that shows through at ~50% opacity on the main editor canvas.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import os

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

DEFAULT_PATH = "arduino_font.txt"

WIDTH     = 10
HEIGHT    = 16
CELL_SIZE = 22
PADDING   = 6

# Colors
COLOR_ON      = "#000000"   # drawn pixel (solid black)
COLOR_OFF     = "#FFFFFF"   # empty pixel (white)
COLOR_GRID    = "#BBBBBB"   # grid line colour


def blend_hex(fg_hex, bg_hex="#FFFFFF", alpha=0.30):
    """Blend fg over bg at given alpha, return #RRGGBB string."""
    def h(hx):
        hx = hx.lstrip("#")
        return int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16)
    fr, fg, fb = h(fg_hex)
    br, bg, bb = h(bg_hex)
    r = int(fr * alpha + br * (1 - alpha))
    g = int(fg * alpha + bg * (1 - alpha))
    b = int(fb * alpha + bb * (1 - alpha))
    return f"#{r:02X}{g:02X}{b:02X}"


# Soft blue ghost: 30 % #0055FF over white
GHOST_COLOR = blend_hex("#0055FF", "#FFFFFF", 0.30)


class FontEditor:
    def __init__(self, root):
        self.root = root
        root.title("10x16 Arduino Font Editor – Egemen Tutkun")

        # Reference font (ghost overlay) – None means no overlay loaded
        self.ref_glyphs = None
        self.show_ref   = tk.BooleanVar(value=True)

        # --- Glyph grid settings ---
        self.grid_cell_size = 5
        self.grid_cols = 16
        self.grid_rows = ((126 - 32 + 1) + self.grid_cols - 1) // self.grid_cols

        grid_width  = self.grid_cols * (WIDTH  * self.grid_cell_size + 6) + 20
        grid_height = self.grid_rows * (HEIGHT * self.grid_cell_size + 18) + 20

        total_width  = WIDTH * CELL_SIZE + PADDING * 2 + grid_width + 260
        total_height = max(HEIGHT * CELL_SIZE + PADDING * 2, grid_height) + 140
        root.geometry(f"{total_width}x{total_height}")

        # === MAIN EDITOR CANVAS ===
        self.canvas = tk.Canvas(root,
                                width=WIDTH  * CELL_SIZE + PADDING * 2,
                                height=HEIGHT * CELL_SIZE + PADDING * 2,
                                bg="#E0E0E0")
        self.canvas.grid(row=0, column=0, columnspan=4, padx=8, pady=8, sticky="n")

        # Two rectangle layers per cell: ghost (back) and user pixel (front)
        self.ghost_rects = [[None] * WIDTH for _ in range(HEIGHT)]
        self.rects       = [[None] * WIDTH for _ in range(HEIGHT)]
        self._draw_grid()

        # === GLYPH GRID VIEW ===
        self.grid_canvas = tk.Canvas(root, width=grid_width, height=grid_height, bg="white")
        self.grid_canvas.grid(row=0, column=4, rowspan=5, padx=8, pady=8, sticky="n")
        self.grid_canvas.bind("<Button-1>", self.on_click_grid)

        # === DATA ===
        self.glyphs      = {}
        self.order       = []
        self.current_ord = ord('A')

        # Mouse bindings
        self.canvas.bind("<Button-1>",  self.on_click)
        self.canvas.bind("<Button-3>",  self.on_right_click)
        self.canvas.bind("<B1-Motion>", self.on_drag_draw)
        self.canvas.bind("<B3-Motion>", self.on_drag_erase)

        # ── Row 1: character navigation ──
        tk.Label(root, text="Character:").grid(row=1, column=0, sticky="e")
        self.char_entry = tk.Entry(root, width=4)
        self.char_entry.grid(row=1, column=1, sticky="w")
        self.char_entry.insert(0, chr(self.current_ord))
        self.char_entry.bind("<Return>", lambda e: self.select_char_from_entry())
        tk.Button(root, text="Prev", command=self.prev_char).grid(row=1, column=2)
        tk.Button(root, text="Next", command=self.next_char).grid(row=1, column=3)

        # ── Row 2: file operations ──
        tk.Button(root, text="Load file…",   command=self.load_file).grid(row=2, column=0)
        tk.Button(root, text="Save file…",   command=self.save_file).grid(row=2, column=1)
        tk.Button(root, text="Export .h…",   command=self.export_arduino).grid(row=2, column=2)
        tk.Button(root, text="Test pattern", command=self.fill_test).grid(row=2, column=3)
        tk.Button(root, text="Import TTF…",  command=self.import_ttf,
                  bg="#DDFFD8", relief="groove").grid(row=2, column=1)

        # ── Row 3: reference / ghost controls ──
        ref_frame = tk.Frame(root)
        ref_frame.grid(row=3, column=0, columnspan=4, sticky="w", padx=8, pady=(4, 0))

        tk.Button(ref_frame, text="Load reference font…",
                  command=self.load_ref_font,
                  bg="#DDEEFF", relief="groove").pack(side="left", padx=(0, 4))
        tk.Button(ref_frame, text="Clear reference",
                  command=self.clear_ref_font,
                  relief="groove").pack(side="left", padx=(0, 8))
        tk.Checkbutton(ref_frame, text="Show ghost overlay",
                       variable=self.show_ref,
                       command=self._update_canvas).pack(side="left")

        self.ref_label = tk.Label(ref_frame, text="No reference loaded",
                                  fg="gray", font=("Arial", 8))
        self.ref_label.pack(side="left", padx=8)

        # ── Row 4: byte preview ──
        self.preview_label = tk.Label(root, text="", font=("Courier", 9), justify="left")
        self.preview_label.grid(row=4, column=0, columnspan=4, pady=(4, 0),
                                sticky="w", padx=8)

        root.bind("<Left>",  lambda e: self.prev_char())
        root.bind("<Right>", lambda e: self.next_char())
        root.bind("s",       lambda e: self.save_file())

        self._ensure_defaults()

        if os.path.exists(DEFAULT_PATH):
            try:
                self.parse_file(DEFAULT_PATH)
                messagebox.showinfo("Loaded", f"Loaded default font:\n{DEFAULT_PATH}")
            except Exception as ex:
                print("Could not load default font:", ex)

        self.select_char(self.current_ord)

    # ──────────────────────────────────────────────
    # TTF import
    # ──────────────────────────────────────────────

    def import_ttf(self):
        if not _PIL_AVAILABLE:
            messagebox.showerror(
                "Pillow not found",
                "Pillow is required to import TTF fonts.\n\n"
                "Install it with:\n  pip install pillow")
            return

        path = filedialog.askopenfilename(
            title="Import TrueType font",
            filetypes=[("TrueType / OpenType fonts", "*.ttf *.otf"), ("All files", "*.*")])
        if not path:
            return

        # Ask the user for a font size to try; default gives a good fit for 10×16
        size = simpledialog.askinteger(
            "Font size",
            "Pixel size to render the font at\n(try values between 12 and 16):",
            initialvalue=14, minvalue=4, maxvalue=64, parent=self.root)
        if size is None:
            return

        threshold = simpledialog.askinteger(
            "Threshold",
            "Brightness threshold (0-255).\n"
            "Pixels darker than this become ON bits.\n"
            "(128 is a good starting point)",
            initialvalue=128, minvalue=1, maxvalue=254, parent=self.root)
        if threshold is None:
            return

        try:
            font = ImageFont.truetype(path, size)
        except Exception as ex:
            messagebox.showerror("Error", f"Could not load font:\n{ex}")
            return

        imported = {}
        for code in range(32, 127):
            ch = chr(code)
            # Render into a slightly larger canvas, then crop/resize to 10×16
            img = Image.new("L", (WIDTH * 4, HEIGHT * 4), color=255)
            draw = ImageDraw.Draw(img)
            draw.text((0, 0), ch, font=font, fill=0)

            # Auto-crop to content bounding box (with fallback to full image)
            bbox = img.getbbox()
            if bbox and ch.strip():          # skip whitespace characters
                img = img.crop(bbox)

            # Resize to exactly 10×16 using high-quality downsampling
            img = img.resize((WIDTH, HEIGHT), Image.LANCZOS)

            # Threshold → binary row strings
            glyph = []
            for r in range(HEIGHT):
                row = ""
                for c in range(WIDTH):
                    row += "1" if img.getpixel((c, r)) < threshold else "0"
                glyph.append(row)
            imported[code] = glyph

        self.glyphs = imported
        self.order  = sorted(imported.keys())
        self._ensure_defaults()
        self.select_char(self.current_ord)
        messagebox.showinfo(
            "Imported",
            f"Imported {len(imported)} glyphs from:\n{os.path.basename(path)}\n\n"
            "Tip: You can now fine-tune individual glyphs and Save or Export .h")

    # ──────────────────────────────────────────────
    # Reference font
    # ──────────────────────────────────────────────

    def load_ref_font(self):
        path = filedialog.askopenfilename(
            title="Load reference / template font",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            ref = self._parse_font_file(path)
            # fill blanks so every ASCII 32-126 is present
            for o in range(32, 127):
                if o not in ref:
                    ref[o] = ["0" * WIDTH for _ in range(HEIGHT)]
            self.ref_glyphs = ref
            self.ref_label.config(text=f"Reference: {os.path.basename(path)}", fg="#0055AA")
            self.show_ref.set(True)
            self._update_canvas()
            self.update_glyph_grid()
        except Exception as ex:
            messagebox.showerror("Error", f"Failed to load reference font:\n{ex}")

    def clear_ref_font(self):
        self.ref_glyphs = None
        self.ref_label.config(text="No reference loaded", fg="gray")
        self._update_canvas()
        self.update_glyph_grid()

    def _parse_font_file(self, path):
        """Parse a .txt font file, return dict {ord_value: [row_strings]}."""
        glyphs = {}
        with open(path, "r", encoding="utf-8") as f:
            lines = [L.rstrip("\n") for L in f]
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            if line.startswith("CHAR"):
                parts = line.split(None, 2)
                code = int(parts[1])
                i += 1
                glyph = []
                for _ in range(HEIGHT):
                    if i >= len(lines):
                        raise ValueError("Unexpected EOF while reading glyph")
                    row = lines[i].strip().ljust(WIDTH, "0")[:WIDTH]
                    glyph.append(row)
                    i += 1
                glyphs[code] = glyph
            else:
                i += 1
        return glyphs

    # ──────────────────────────────────────────────
    # Utility
    # ──────────────────────────────────────────────

    def _ensure_defaults(self):
        for o in range(32, 127):
            if o not in self.glyphs:
                self.glyphs[o] = ["0" * WIDTH for _ in range(HEIGHT)]
        if not self.order:
            self.order = list(range(32, 127))

    def _draw_grid(self):
        """Create ghost-layer then user-layer rectangles for every cell."""
        for r in range(HEIGHT):
            for c in range(WIDTH):
                x1 = PADDING + c * CELL_SIZE
                y1 = PADDING + r * CELL_SIZE
                x2 = x1 + CELL_SIZE - 2
                y2 = y1 + CELL_SIZE - 2

                # Ghost rectangle – drawn first so it sits behind the user rect
                ghost = self.canvas.create_rectangle(
                    x1, y1, x2, y2,
                    fill=COLOR_OFF, outline=COLOR_GRID, width=1)
                self.ghost_rects[r][c] = ghost

                # User pixel rectangle – starts invisible (empty fill)
                rect = self.canvas.create_rectangle(
                    x1, y1, x2, y2,
                    fill="", outline="")
                self.rects[r][c] = rect

    def _set_pixel(self, row, col, value):
        glyph = self.glyphs.setdefault(self.current_ord,
                                       ["0" * WIDTH for _ in range(HEIGHT)])
        line = list(glyph[row])
        if line[col] != value:
            line[col] = value
            glyph[row] = "".join(line)
            self.glyphs[self.current_ord] = glyph
            self._update_canvas()
            self._update_preview()
            self.update_glyph_grid()

    def _cell_from_event(self, event):
        x = event.x - PADDING
        y = event.y - PADDING
        if x < 0 or y < 0:
            return None, None
        c = x // CELL_SIZE
        r = y // CELL_SIZE
        if 0 <= c < WIDTH and 0 <= r < HEIGHT:
            return r, c
        return None, None

    # ──────────────────────────────────────────────
    # Editor canvas interaction
    # ──────────────────────────────────────────────

    def on_click(self, event):
        r, c = self._cell_from_event(event)
        if r is not None:
            glyph = self.glyphs[self.current_ord]
            new_val = "1" if glyph[r][c] == "0" else "0"
            self._set_pixel(r, c, new_val)

    def on_right_click(self, event):
        r, c = self._cell_from_event(event)
        if r is not None:
            self._set_pixel(r, c, "0")

    def on_drag_draw(self, event):
        r, c = self._cell_from_event(event)
        if r is not None:
            self._set_pixel(r, c, "1")

    def on_drag_erase(self, event):
        r, c = self._cell_from_event(event)
        if r is not None:
            self._set_pixel(r, c, "0")

    def _update_canvas(self):
        """Repaint the main editor canvas with ghost layer + user pixels."""
        glyph = self.glyphs.get(self.current_ord,
                                 ["0" * WIDTH for _ in range(HEIGHT)])

        # Reference glyph for ghost (None when overlay is off or not loaded)
        ref = None
        if self.ref_glyphs is not None and self.show_ref.get():
            ref = self.ref_glyphs.get(self.current_ord,
                                       ["0" * WIDTH for _ in range(HEIGHT)])

        for r in range(HEIGHT):
            for c in range(WIDTH):
                user_on = glyph[r][c] == "1"

                # ── Ghost / reference layer ──
                if ref is not None and ref[r][c] == "1":
                    ghost_fill = GHOST_COLOR   # soft blue-tinted ghost pixel
                else:
                    ghost_fill = COLOR_OFF     # plain white

                self.canvas.itemconfig(self.ghost_rects[r][c],
                                       fill=ghost_fill, outline=COLOR_GRID)

                # ── User pixel layer ──
                # When a user pixel is ON, paint it solid black (hides ghost)
                # When OFF, make fill empty so the ghost rectangle shows through
                if user_on:
                    self.canvas.itemconfig(self.rects[r][c],
                                           fill=COLOR_ON, outline="")
                else:
                    self.canvas.itemconfig(self.rects[r][c],
                                           fill="", outline="")

    # ──────────────────────────────────────────────
    # Byte export helpers
    # ──────────────────────────────────────────────

    def _glyph_to_bytes(self, glyph):
        """
        10×16 → 32 bytes (2 bytes / row, MSB-first).
        Each row's 10 bits are left-aligned in a 16-bit big-endian word.
        """
        result = []
        for row in glyph:
            word = 0
            for c, bit in enumerate(row):
                if bit == "1":
                    word |= (1 << (WIDTH - 1 - c))
            word <<= (16 - WIDTH)
            result.append((word >> 8) & 0xFF)
            result.append(word & 0xFF)
        return result

    def _update_preview(self):
        glyph = self.glyphs.get(self.current_ord,
                                 ["0" * WIDTH for _ in range(HEIGHT)])
        byt     = self._glyph_to_bytes(glyph)
        wrapped = ""
        for i in range(0, len(byt), 8):
            wrapped += "  " + ", ".join(f"0x{b:02X}" for b in byt[i:i+8]) + ",\n"
        txt = (f"CHAR {self.current_ord} '{chr(self.current_ord)}'  "
               f"({WIDTH}×{HEIGHT}, {len(byt)} bytes)\n{wrapped}")
        self.preview_label.config(text=txt)

    # ──────────────────────────────────────────────
    # Glyph navigation
    # ──────────────────────────────────────────────

    def select_char_from_entry(self):
        txt = self.char_entry.get()
        if txt:
            self.select_char(ord(txt[0]))

    def select_char(self, ord_value):
        if ord_value not in self.glyphs:
            self.glyphs[ord_value] = ["0" * WIDTH for _ in range(HEIGHT)]
            if ord_value not in self.order:
                self.order.append(ord_value)
        self.current_ord = ord_value
        self.char_entry.delete(0, tk.END)
        try:
            self.char_entry.insert(0, chr(self.current_ord))
        except Exception:
            self.char_entry.insert(0, f"#{self.current_ord}")
        self._update_canvas()
        self._update_preview()
        self.update_glyph_grid()

    def prev_char(self):
        idx = self.order.index(self.current_ord)
        self.select_char(self.order[(idx - 1) % len(self.order)])

    def next_char(self):
        idx = self.order.index(self.current_ord)
        self.select_char(self.order[(idx + 1) % len(self.order)])

    # ──────────────────────────────────────────────
    # File I/O
    # ──────────────────────────────────────────────

    def load_file(self):
        path = filedialog.askopenfilename(
            title="Open font file",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.parse_file(path)
            messagebox.showinfo("Loaded", f"Loaded: {path}")
            self._ensure_defaults()
            self.select_char(self.current_ord)
        except Exception as ex:
            messagebox.showerror("Error", f"Failed to load file:\n{ex}")

    def parse_file(self, path):
        glyphs      = self._parse_font_file(path)
        self.glyphs = glyphs
        self.order  = sorted(glyphs.keys())

    def save_file(self):
        path = filedialog.asksaveasfilename(
            title="Save font file",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            self._write_text_file(path)
            messagebox.showinfo("Saved", f"Saved to: {path}")
        except Exception as ex:
            messagebox.showerror("Error", f"Failed to save:\n{ex}")

    def _write_text_file(self, path):
        with open(path, "w", encoding="utf-8") as f:
            for code in self.order:
                glyph = self.glyphs.get(code, ["0" * WIDTH for _ in range(HEIGHT)])
                ch   = chr(code)
                name = f"'{ch}'" if ch.isprintable() else ""
                f.write(f"CHAR {code} {name}\n")
                for row in glyph:
                    f.write(row + "\n")
                f.write("\n")

    # ──────────────────────────────────────────────
    # Arduino .h export
    # ──────────────────────────────────────────────

    def export_arduino(self):
        path = filedialog.asksaveasfilename(
            title="Export Arduino header",
            defaultextension=".h",
            filetypes=[("C/C++ header", "*.h"), ("All files", "*.*")])
        if not path:
            return
        try:
            self._ensure_defaults()
            self._write_arduino_header(path)
            messagebox.showinfo("Exported", f"Arduino header written to:\n{path}")
        except Exception as ex:
            messagebox.showerror("Error", f"Failed to export:\n{ex}")

    def _write_arduino_header(self, path):
        guard           = os.path.basename(path).upper().replace(".", "_").replace("-", "_")
        bytes_per_glyph = HEIGHT * 2

        with open(path, "w", encoding="utf-8") as f:
            f.write("// Arduino 10×16 bitmap font\n")
            f.write("// Generated by Arduino Font Editor\n")
            f.write(f"// {bytes_per_glyph} bytes per glyph, MSB-first, row-major\n")
            f.write("// First glyph = ASCII 32 (space)\n\n")
            f.write(f"#ifndef {guard}\n#define {guard}\n\n")
            f.write("#include <pgmspace.h>\n\n")
            f.write(f"#define FONT_WIDTH  {WIDTH}\n")
            f.write(f"#define FONT_HEIGHT {HEIGHT}\n")
            f.write("#define FONT_FIRST  32\n")
            f.write("#define FONT_LAST   126\n\n")
            f.write("const uint8_t font10x16[] PROGMEM = {\n")

            for code in range(32, 127):
                glyph = self.glyphs.get(code, ["0" * WIDTH for _ in range(HEIGHT)])
                byt   = self._glyph_to_bytes(glyph)
                ch    = chr(code)
                label = f"'{ch}'" if ch.isprintable() and ch != "'" else f"#{code}"
                f.write(f"  // {label} (ASCII {code})\n")
                for i in range(0, len(byt), 8):
                    f.write("  " + ", ".join(f"0x{b:02X}" for b in byt[i:i+8]) + ",\n")

            f.write("};\n\n")
            f.write("// Usage helper:\n")
            f.write("// const uint8_t* glyphPtr(char c) {\n")
            f.write(f"//   return font10x16 + (c - FONT_FIRST) * {bytes_per_glyph};\n")
            f.write("// }\n\n")
            f.write(f"#endif // {guard}\n")

    # ──────────────────────────────────────────────
    # Glyph grid view
    # ──────────────────────────────────────────────

    def update_glyph_grid(self):
        self.grid_canvas.delete("all")
        size   = self.grid_cell_size
        cell_w = WIDTH  * size + 6
        cell_h = HEIGHT * size + 18

        for idx, code in enumerate(range(32, 127)):
            glyph = self.glyphs.get(code, ["0" * WIDTH for _ in range(HEIGHT)])
            col   = idx % self.grid_cols
            row   = idx // self.grid_cols
            x0    = col * cell_w + 10
            y0    = row * cell_h + 10

            # Ghost layer in grid view too
            if self.ref_glyphs and self.show_ref.get():
                ref = self.ref_glyphs.get(code, ["0" * WIDTH for _ in range(HEIGHT)])
                for r in range(HEIGHT):
                    for c in range(WIDTH):
                        if ref[r][c] == "1":
                            x1 = x0 + c * size
                            y1 = y0 + r * size
                            self.grid_canvas.create_rectangle(
                                x1, y1, x1 + size, y1 + size,
                                fill=GHOST_COLOR, outline="")

            # User glyph on top
            for r in range(HEIGHT):
                for c in range(WIDTH):
                    if glyph[r][c] == "1":
                        x1 = x0 + c * size
                        y1 = y0 + r * size
                        self.grid_canvas.create_rectangle(
                            x1, y1, x1 + size, y1 + size,
                            fill="black", outline="")

            self.grid_canvas.create_text(
                x0 + (WIDTH * size) // 2, y0 + HEIGHT * size + 8,
                text=chr(code), font=("Arial", 7))

            if code == self.current_ord:
                self.grid_canvas.create_rectangle(
                    x0 - 2, y0 - 2,
                    x0 + WIDTH * size + 2, y0 + HEIGHT * size + 14,
                    outline="red", width=2)

    def on_click_grid(self, event):
        size   = self.grid_cell_size
        cell_w = WIDTH  * size + 6
        cell_h = HEIGHT * size + 18

        for idx, code in enumerate(range(32, 127)):
            col = idx % self.grid_cols
            row = idx // self.grid_cols
            x0  = col * cell_w + 10
            y0  = row * cell_h + 10
            x1  = x0 + WIDTH  * size
            y1  = y0 + HEIGHT * size + 14
            if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                self.select_char(code)
                break

    # ──────────────────────────────────────────────
    # Test
    # ──────────────────────────────────────────────

    def fill_test(self):
        """Checkerboard pattern to verify byte output."""
        pattern = []
        for r in range(HEIGHT):
            row = ""
            for c in range(WIDTH):
                row += "1" if (r + c) % 2 == 0 else "0"
            pattern.append(row)
        self.glyphs[self.current_ord] = pattern
        self._update_canvas()
        self._update_preview()
        self.update_glyph_grid()


if __name__ == "__main__":
    root = tk.Tk()
    app = FontEditor(root)
    root.mainloop()