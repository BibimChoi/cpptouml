"""
C++ to PlantUML Converter
Main application with Tkinter GUI
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import webbrowser
import urllib.parse
import urllib.request
import zlib
import io
from pathlib import Path

# Try to import PIL for image display
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from cpp_parser import CppParser
from relationship import RelationshipAnalyzer
from plantuml_generator import PlantUMLGenerator

# Try to import libclang parser
try:
    from cpp_parser_clang import CppParserClang, is_available as clang_available
    HAS_CLANG = clang_available()
except ImportError:
    HAS_CLANG = False
    CppParserClang = None


class Cpp2PlantUMLApp:
    def __init__(self, root):
        self.root = root
        self.root.title("C++ to PlantUML Converter")
        self.root.geometry("1000x700")
        self.root.minsize(800, 600)

        # State
        self.parser = None
        self.generator = None
        self.class_vars = {}  # Checkbutton variables
        self.class_widgets = {}  # Checkbutton widgets for filtering
        self.current_plantuml = ""  # Store current PlantUML code
        self.current_image = None  # Store current image for display

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Top section: Project settings
        settings_frame = ttk.LabelFrame(main_frame, text="Settings", padding="10")
        settings_frame.pack(fill=tk.X, pady=(0, 10))

        # Project folder
        ttk.Label(settings_frame, text="Project Folder:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.folder_var = tk.StringVar()
        folder_entry = ttk.Entry(settings_frame, textvariable=self.folder_var, width=60)
        folder_entry.grid(row=0, column=1, padx=5, pady=2, sticky=tk.EW)
        ttk.Button(settings_frame, text="Browse...", command=self._browse_folder).grid(row=0, column=2, pady=2)

        # Start class and depth
        ttk.Label(settings_frame, text="Start Class:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.start_class_var = tk.StringVar()
        self.start_class_combo = ttk.Combobox(settings_frame, textvariable=self.start_class_var, width=57)
        self.start_class_combo.grid(row=1, column=1, padx=5, pady=2, sticky=tk.EW)

        depth_frame = ttk.Frame(settings_frame)
        depth_frame.grid(row=1, column=2, pady=2)
        ttk.Label(depth_frame, text="Depth:").pack(side=tk.LEFT)
        self.depth_var = tk.IntVar(value=3)
        depth_spin = ttk.Spinbox(depth_frame, from_=1, to=10, textvariable=self.depth_var, width=5)
        depth_spin.pack(side=tk.LEFT, padx=5)

        # Parser mode selection
        ttk.Label(settings_frame, text="Parser Mode:").grid(row=2, column=0, sticky=tk.W, pady=2)
        mode_frame = ttk.Frame(settings_frame)
        mode_frame.grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)

        self.parser_mode = tk.StringVar(value="regex")
        ttk.Radiobutton(mode_frame, text="Regex (빠름, 설치 불필요)",
                        variable=self.parser_mode, value="regex",
                        command=self._on_parser_mode_changed).pack(side=tk.LEFT, padx=(0, 15))
        self.clang_radio = ttk.Radiobutton(mode_frame, text="libclang (정확함, LLVM 필요)",
                        variable=self.parser_mode, value="clang",
                        command=self._on_parser_mode_changed)
        self.clang_radio.pack(side=tk.LEFT)

        if not HAS_CLANG:
            self.clang_radio.configure(state=tk.DISABLED)
            ttk.Label(mode_frame, text="(clang 미설치)", foreground="gray").pack(side=tk.LEFT, padx=5)

        # libclang path (hidden by default, shown when clang mode selected)
        self.clang_path_label = ttk.Label(settings_frame, text="libclang Path:")
        self.clang_path_var = tk.StringVar()
        self.clang_path_entry = ttk.Entry(settings_frame, textvariable=self.clang_path_var, width=60)
        self.clang_path_btn = ttk.Button(settings_frame, text="Browse...", command=self._browse_libclang)

        settings_frame.columnconfigure(1, weight=1)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(btn_frame, text="Parse Project", command=self._parse_project).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Generate Diagram", command=self._generate_diagram).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Generate All Classes", command=self._generate_all).pack(side=tk.LEFT, padx=5)

        # Middle section: Class list and PlantUML output
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)

        # Left: Class list
        left_frame = ttk.LabelFrame(content_frame, text="Classes", padding="5")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 5))

        # Search box
        search_frame = ttk.Frame(left_frame)
        search_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self._on_search_changed)
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=20)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        # Scrollable class list
        self.class_canvas = tk.Canvas(left_frame, width=200)
        class_scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.class_canvas.yview)
        self.class_list_frame = ttk.Frame(self.class_canvas)

        self.class_canvas.configure(yscrollcommand=class_scrollbar.set)
        class_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.class_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.class_canvas_window = self.class_canvas.create_window((0, 0), window=self.class_list_frame, anchor=tk.NW)
        self.class_list_frame.bind("<Configure>", self._on_class_frame_configure)

        # Select all / none buttons
        select_frame = ttk.Frame(left_frame)
        select_frame.pack(fill=tk.X, pady=5)
        ttk.Button(select_frame, text="All", command=self._select_all, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Button(select_frame, text="None", command=self._select_none, width=6).pack(side=tk.LEFT, padx=2)

        # Right: PlantUML output
        right_frame = ttk.LabelFrame(content_frame, text="PlantUML Output", padding="5")
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Toggle buttons for text/image view
        toggle_frame = ttk.Frame(right_frame)
        toggle_frame.pack(fill=tk.X, pady=(0, 5))

        self.view_mode = tk.StringVar(value="text")
        ttk.Radiobutton(toggle_frame, text="Text", variable=self.view_mode,
                        value="text", command=self._toggle_view).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(toggle_frame, text="Image", variable=self.view_mode,
                        value="image", command=self._toggle_view).pack(side=tk.LEFT, padx=5)

        if not HAS_PIL:
            ttk.Label(toggle_frame, text="(Install Pillow for image view)",
                      foreground="gray").pack(side=tk.LEFT, padx=10)

        # Container for text/image views
        self.output_container = ttk.Frame(right_frame)
        self.output_container.pack(fill=tk.BOTH, expand=True)

        # Text view
        self.text_frame = ttk.Frame(self.output_container)
        self.text_frame.pack(fill=tk.BOTH, expand=True)

        # Text area with line numbers
        text_container = ttk.Frame(self.text_frame)
        text_container.pack(fill=tk.BOTH, expand=True)

        # Line numbers widget
        self.line_numbers = tk.Text(text_container, width=4, padx=5, pady=5,
                                     font=("Consolas", 10), bg="#f0f0f0", fg="#888888",
                                     state=tk.DISABLED, takefocus=0)
        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)

        # Main text widget
        self.output_text = tk.Text(text_container, wrap=tk.NONE, font=("Consolas", 10), padx=5, pady=5)
        self.output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Vertical scrollbar
        v_scroll = ttk.Scrollbar(text_container, orient=tk.VERTICAL, command=self._sync_scroll)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.output_text.configure(yscrollcommand=lambda *args: self._on_text_scroll(v_scroll, *args))

        # Horizontal scrollbar
        h_scroll = ttk.Scrollbar(self.text_frame, orient=tk.HORIZONTAL, command=self.output_text.xview)
        h_scroll.pack(fill=tk.X)
        self.output_text.configure(xscrollcommand=h_scroll.set)

        # Bind events for line number updates
        self.output_text.bind("<KeyRelease>", self._update_line_numbers)
        self.output_text.bind("<MouseWheel>", self._update_line_numbers)

        # Image view (hidden by default)
        self.image_frame = ttk.Frame(self.output_container)

        self.image_canvas = tk.Canvas(self.image_frame, bg="white")
        self.image_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        img_v_scroll = ttk.Scrollbar(self.image_frame, orient=tk.VERTICAL, command=self.image_canvas.yview)
        img_v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        img_h_scroll = ttk.Scrollbar(self.image_frame, orient=tk.HORIZONTAL, command=self.image_canvas.xview)
        img_h_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.image_canvas.configure(yscrollcommand=img_v_scroll.set, xscrollcommand=img_h_scroll.set)

        # Bottom: Action buttons
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(action_frame, text="Copy to Clipboard", command=self._copy_to_clipboard).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="Save to File", command=self._save_to_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="Preview Online", command=self._preview_online).pack(side=tk.LEFT, padx=5)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, pady=(10, 0))

    def _on_class_frame_configure(self, event):
        """Update canvas scroll region."""
        self.class_canvas.configure(scrollregion=self.class_canvas.bbox("all"))

    def _browse_folder(self):
        """Browse for project folder."""
        folder = filedialog.askdirectory(title="Select C++ Project Folder")
        if folder:
            self.folder_var.set(folder)

    def _on_parser_mode_changed(self):
        """Show/hide libclang path input based on parser mode."""
        if self.parser_mode.get() == "clang":
            self.clang_path_label.grid(row=3, column=0, sticky=tk.W, pady=2)
            self.clang_path_entry.grid(row=3, column=1, padx=5, pady=2, sticky=tk.EW)
            self.clang_path_btn.grid(row=3, column=2, pady=2)
        else:
            self.clang_path_label.grid_forget()
            self.clang_path_entry.grid_forget()
            self.clang_path_btn.grid_forget()

    def _browse_libclang(self):
        """Browse for libclang library."""
        filetypes = [("DLL files", "*.dll"), ("SO files", "*.so"), ("All files", "*.*")]
        file_path = filedialog.askopenfilename(title="Select libclang", filetypes=filetypes)
        if file_path:
            self.clang_path_var.set(file_path)

    def _parse_project(self):
        """Parse the C++ project."""
        folder = self.folder_var.get()
        if not folder:
            messagebox.showerror("Error", "Please select a project folder.")
            return

        if not Path(folder).is_dir():
            messagebox.showerror("Error", "Selected path is not a directory.")
            return

        self.status_var.set("Parsing project...")
        self.root.update()

        def do_parse():
            try:
                # Select parser based on mode
                if self.parser_mode.get() == "clang":
                    libclang_path = self.clang_path_var.get() or None
                    self.parser = CppParserClang(libclang_path)
                    mode_name = "libclang"
                else:
                    self.parser = CppParser()
                    mode_name = "Regex"

                count = self.parser.parse_directory(folder)
                self.generator = PlantUMLGenerator(self.parser)

                # Update UI in main thread
                self.root.after(0, lambda: self._update_class_list(count, mode_name))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Parse Error", str(e)))
                self.root.after(0, lambda: self.status_var.set("Parse failed"))

        threading.Thread(target=do_parse, daemon=True).start()

    def _update_class_list(self, count, mode_name="Regex"):
        """Update the class list after parsing."""
        # Clear existing
        for widget in self.class_list_frame.winfo_children():
            widget.destroy()
        self.class_vars.clear()
        self.class_widgets = {}  # Store widgets for filtering

        # Add new checkbuttons
        class_names = sorted(self.parser.get_class_names())
        for name in class_names:
            var = tk.BooleanVar(value=True)
            self.class_vars[name] = var
            cb = ttk.Checkbutton(self.class_list_frame, text=name, variable=var)
            cb.pack(anchor=tk.W)
            self.class_widgets[name] = cb

        # Update combobox
        self.start_class_combo['values'] = class_names
        if class_names:
            self.start_class_var.set(class_names[0])

        # Clear search
        self.search_var.set("")

        self.status_var.set(f"[{mode_name}] Parsed {count} files, found {len(class_names)} classes")

    def _on_search_changed(self, *args):
        """Filter class list based on search text."""
        if not hasattr(self, 'class_widgets'):
            return

        search_text = self.search_var.get().lower()

        for name, widget in self.class_widgets.items():
            if search_text in name.lower():
                widget.pack(anchor=tk.W)
            else:
                widget.pack_forget()

        # Update scroll region
        self.class_list_frame.update_idletasks()
        self.class_canvas.configure(scrollregion=self.class_canvas.bbox("all"))

    def _select_all(self):
        """Select all classes."""
        for var in self.class_vars.values():
            var.set(True)

    def _select_none(self):
        """Deselect all classes."""
        for var in self.class_vars.values():
            var.set(False)

    def _generate_diagram(self):
        """Generate diagram from start class with depth limit."""
        if not self.parser or not self.generator:
            messagebox.showerror("Error", "Please parse a project first.")
            return

        start_class = self.start_class_var.get()
        if not start_class:
            messagebox.showerror("Error", "Please select a start class.")
            return

        if start_class not in self.parser.classes:
            messagebox.showerror("Error", f"Class '{start_class}' not found.")
            return

        depth = self.depth_var.get()
        self.status_var.set(f"Generating diagram from {start_class}...")
        self.root.update()

        try:
            plantuml = self.generator.generate_from_class(start_class, depth)
            self.current_plantuml = plantuml
            self.output_text.delete("1.0", tk.END)
            self.output_text.insert("1.0", plantuml)
            self._update_line_numbers()
            self.status_var.set(f"Generated diagram for {start_class} (depth={depth})")

            # If in image mode, refresh the image
            if self.view_mode.get() == "image":
                self._fetch_and_show_image()
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.status_var.set("Generation failed")

    def _generate_all(self):
        """Generate diagram for all selected classes."""
        if not self.parser or not self.generator:
            messagebox.showerror("Error", "Please parse a project first.")
            return

        selected = [name for name, var in self.class_vars.items() if var.get()]
        if not selected:
            messagebox.showerror("Error", "Please select at least one class.")
            return

        self.status_var.set("Generating diagram for all selected classes...")
        self.root.update()

        try:
            analyzer = RelationshipAnalyzer(self.parser)

            # Get relationships only for selected classes
            all_rels = []
            for class_name in selected:
                if class_name in self.parser.classes:
                    class_info = self.parser.classes[class_name]
                    rels = analyzer._analyze_class(class_info)
                    # Filter to only include relationships between selected classes
                    for rel in rels:
                        if rel.from_class in selected and rel.to_class in selected:
                            all_rels.append(rel)

            # Remove duplicates
            seen = set()
            unique_rels = []
            for rel in all_rels:
                key = (rel.from_class, rel.to_class, rel.rel_type)
                if key not in seen:
                    seen.add(key)
                    unique_rels.append(rel)

            plantuml = self.generator.generate(set(selected), unique_rels, "Selected Classes Diagram")
            self.current_plantuml = plantuml
            self.output_text.delete("1.0", tk.END)
            self.output_text.insert("1.0", plantuml)
            self._update_line_numbers()
            self.status_var.set(f"Generated diagram for {len(selected)} classes")

            # If in image mode, refresh the image
            if self.view_mode.get() == "image":
                self._fetch_and_show_image()
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.status_var.set("Generation failed")

    def _copy_to_clipboard(self):
        """Copy PlantUML to clipboard."""
        content = self.output_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("Warning", "No content to copy.")
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.status_var.set("Copied to clipboard")

    def _save_to_file(self):
        """Save PlantUML to file."""
        content = self.output_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("Warning", "No content to save.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".puml",
            filetypes=[("PlantUML files", "*.puml"), ("Text files", "*.txt"), ("All files", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.status_var.set(f"Saved to {file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {e}")

    def _preview_online(self):
        """Preview diagram on PlantUML online server."""
        content = self.output_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("Warning", "No content to preview.")
            return

        # Use PlantUML web server
        encoded = urllib.parse.quote(content)
        url = f"http://www.plantuml.com/plantuml/uml/{encoded}"

        # If URL is too long, show warning
        if len(url) > 8000:
            messagebox.showwarning(
                "Warning",
                "The diagram is too large for online preview.\n"
                "Please save to file and use local PlantUML."
            )
            return

        webbrowser.open(url)
        self.status_var.set("Opened preview in browser")

    def _update_line_numbers(self, event=None):
        """Update line numbers in the line number widget."""
        self.line_numbers.configure(state=tk.NORMAL)
        self.line_numbers.delete("1.0", tk.END)

        # Get number of lines
        line_count = int(self.output_text.index('end-1c').split('.')[0])

        # Generate line numbers
        line_numbers_text = "\n".join(str(i) for i in range(1, line_count + 1))
        self.line_numbers.insert("1.0", line_numbers_text)

        self.line_numbers.configure(state=tk.DISABLED)

    def _sync_scroll(self, *args):
        """Sync scrolling between line numbers and text."""
        self.output_text.yview(*args)
        self.line_numbers.yview(*args)

    def _on_text_scroll(self, scrollbar, *args):
        """Handle text scroll and sync line numbers."""
        scrollbar.set(*args)
        self.line_numbers.yview_moveto(args[0])

    def _toggle_view(self):
        """Toggle between text and image view."""
        mode = self.view_mode.get()

        if mode == "text":
            self.image_frame.pack_forget()
            self.text_frame.pack(fill=tk.BOTH, expand=True)
        else:  # image
            if not HAS_PIL:
                messagebox.showwarning(
                    "Pillow Required",
                    "Image view requires Pillow library.\n"
                    "Install it with: pip install Pillow"
                )
                self.view_mode.set("text")
                return

            self.text_frame.pack_forget()
            self.image_frame.pack(fill=tk.BOTH, expand=True)

            # Fetch and show image if we have PlantUML content
            if self.current_plantuml:
                self._fetch_and_show_image()

    def _plantuml_encode(self, text):
        """Encode PlantUML text for the server URL."""
        # Compress with zlib
        compressed = zlib.compress(text.encode('utf-8'), 9)

        # Custom base64 encoding for PlantUML
        chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"

        result = []
        i = 0
        while i < len(compressed):
            if i + 2 < len(compressed):
                b1, b2, b3 = compressed[i], compressed[i+1], compressed[i+2]
                result.append(chars[b1 >> 2])
                result.append(chars[((b1 & 0x3) << 4) | (b2 >> 4)])
                result.append(chars[((b2 & 0xF) << 2) | (b3 >> 6)])
                result.append(chars[b3 & 0x3F])
            elif i + 1 < len(compressed):
                b1, b2 = compressed[i], compressed[i+1]
                result.append(chars[b1 >> 2])
                result.append(chars[((b1 & 0x3) << 4) | (b2 >> 4)])
                result.append(chars[(b2 & 0xF) << 2])
            else:
                b1 = compressed[i]
                result.append(chars[b1 >> 2])
                result.append(chars[(b1 & 0x3) << 4])
            i += 3

        return ''.join(result)

    def _fetch_and_show_image(self):
        """Fetch PlantUML image from server and display it."""
        if not self.current_plantuml:
            return

        self.status_var.set("Fetching diagram image...")
        self.root.update()

        def do_fetch():
            try:
                encoded = self._plantuml_encode(self.current_plantuml)
                url = f"http://www.plantuml.com/plantuml/png/{encoded}"

                # Fetch image
                with urllib.request.urlopen(url, timeout=30) as response:
                    image_data = response.read()

                # Load image with PIL
                image = Image.open(io.BytesIO(image_data))
                self.current_image = ImageTk.PhotoImage(image)

                # Update canvas in main thread
                self.root.after(0, lambda: self._display_image(image.width, image.height))

            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to fetch image: {e}"))
                self.root.after(0, lambda: self.status_var.set("Image fetch failed"))

        threading.Thread(target=do_fetch, daemon=True).start()

    def _display_image(self, width, height):
        """Display the fetched image on canvas."""
        self.image_canvas.delete("all")
        self.image_canvas.create_image(0, 0, anchor=tk.NW, image=self.current_image)
        self.image_canvas.configure(scrollregion=(0, 0, width, height))
        self.status_var.set("Diagram image loaded")


def main():
    root = tk.Tk()
    app = Cpp2PlantUMLApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
