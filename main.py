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
    """
    C++ to PlantUML 변환 애플리케이션의 메인 클래스.

    Tkinter 기반 GUI를 제공하며, C++ 프로젝트를 파싱하여
    PlantUML 클래스 다이어그램으로 변환하는 기능을 제공한다.

    Attributes:
        root: Tkinter root 윈도우
        parser: C++ 파서 인스턴스 (CppParser 또는 CppParserClang)
        generator: PlantUML 생성기 인스턴스
        class_vars: 클래스별 체크박스 변수 딕셔너리
        class_widgets: 클래스별 체크박스 위젯 딕셔너리
        current_plantuml: 현재 생성된 PlantUML 코드
        current_image: 현재 표시 중인 이미지
        rel_filter_vars: 관계 유형 필터 체크박스 변수
        component_filter_vars: 클래스 구성요소 필터 체크박스 변수
    """

    def __init__(self, root):
        """
        애플리케이션을 초기화한다.

        Args:
            root: Tkinter root 윈도우 객체
        """
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

        # Filter options
        self.rel_filter_vars = {}  # Relationship type checkboxes
        self.component_filter_vars = {}  # Class component checkboxes

        self._setup_ui()

    def _setup_ui(self):
        """
        사용자 인터페이스를 구성한다.

        Settings, Filter Options, 버튼, 클래스 목록, PlantUML 출력 영역,
        액션 버튼, 상태바 등 전체 UI 레이아웃을 생성한다.

        UI 구조:
            - Settings: 프로젝트 폴더, 시작 클래스, Depth, 파서 모드
            - Filter Options: 관계 유형 필터, 클래스 구성요소 필터
            - Buttons: Parse Project, Generate Diagram, Generate All Classes
            - Content: 좌측 클래스 목록, 우측 PlantUML 출력
            - Actions: Copy, Save, Preview Online
            - Status Bar: 현재 상태 표시
        """
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

        # Filter Options section
        filter_frame = ttk.LabelFrame(main_frame, text="Filter Options", padding="10")
        filter_frame.pack(fill=tk.X, pady=(0, 10))

        # Relationship type filters (left side)
        rel_frame = ttk.LabelFrame(filter_frame, text="Relationship Types (Depth)", padding="5")
        rel_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        rel_types = [
            ("inheritance", "상속 (Inheritance)"),
            ("composition", "구성 (Composition)"),
            ("aggregation", "집합 (Aggregation)"),
            ("dependency", "의존 (Dependency)")
        ]

        for i, (key, label) in enumerate(rel_types):
            var = tk.BooleanVar(value=False)
            self.rel_filter_vars[key] = var
            cb = ttk.Checkbutton(rel_frame, text=label, variable=var)
            cb.grid(row=i // 2, column=i % 2, sticky=tk.W, padx=5, pady=2)

        # Class component filters (right side)
        comp_frame = ttk.LabelFrame(filter_frame, text="Class Components (Display)", padding="5")
        comp_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        comp_types = [
            ("members", "멤버변수 (Members)"),
            ("methods", "멤버함수 (Methods)")
        ]

        for i, (key, label) in enumerate(comp_types):
            var = tk.BooleanVar(value=False)
            self.component_filter_vars[key] = var
            cb = ttk.Checkbutton(comp_frame, text=label, variable=var)
            cb.grid(row=i, column=0, sticky=tk.W, padx=5, pady=2)

        # Info label
        info_label = ttk.Label(filter_frame, text="※ 선택 안함 또는 모두 선택 = 전체 적용", foreground="gray")
        info_label.pack(side=tk.BOTTOM, pady=(5, 0))

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
        """
        클래스 목록 프레임 크기 변경 시 캔버스 스크롤 영역을 업데이트한다.

        Args:
            event: Configure 이벤트 객체
        """
        self.class_canvas.configure(scrollregion=self.class_canvas.bbox("all"))

    def _browse_folder(self):
        """
        프로젝트 폴더 선택 다이얼로그를 열고 선택된 경로를 설정한다.

        사용자가 폴더를 선택하면 folder_var에 경로가 저장된다.
        """
        folder = filedialog.askdirectory(title="Select C++ Project Folder")
        if folder:
            self.folder_var.set(folder)

    def _on_parser_mode_changed(self):
        """
        파서 모드 변경 시 UI를 업데이트한다.

        libclang 모드 선택 시 libclang 경로 입력 필드를 표시하고,
        Regex 모드 선택 시 해당 필드를 숨긴다.
        """
        if self.parser_mode.get() == "clang":
            self.clang_path_label.grid(row=3, column=0, sticky=tk.W, pady=2)
            self.clang_path_entry.grid(row=3, column=1, padx=5, pady=2, sticky=tk.EW)
            self.clang_path_btn.grid(row=3, column=2, pady=2)
        else:
            self.clang_path_label.grid_forget()
            self.clang_path_entry.grid_forget()
            self.clang_path_btn.grid_forget()

    def _browse_libclang(self):
        """
        libclang 라이브러리 파일 선택 다이얼로그를 연다.

        Windows의 경우 .dll, Linux/Mac의 경우 .so 파일을 선택할 수 있다.
        선택된 경로는 clang_path_var에 저장된다.
        """
        filetypes = [("DLL files", "*.dll"), ("SO files", "*.so"), ("All files", "*.*")]
        file_path = filedialog.askopenfilename(title="Select libclang", filetypes=filetypes)
        if file_path:
            self.clang_path_var.set(file_path)

    def _parse_project(self):
        """
        선택된 C++ 프로젝트를 파싱한다.

        선택된 파서 모드(Regex 또는 libclang)에 따라 적절한 파서를 사용하여
        프로젝트 폴더 내의 모든 C++ 파일을 분석한다.
        파싱은 별도 스레드에서 수행되어 UI가 블로킹되지 않는다.

        파싱 완료 후:
            - 클래스 목록이 UI에 표시됨
            - PlantUML 생성기가 초기화됨
            - Start Class 콤보박스가 업데이트됨

        Raises:
            messagebox.showerror: 폴더가 선택되지 않았거나 유효하지 않은 경우
        """
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
        """
        파싱 완료 후 클래스 목록 UI를 업데이트한다.

        기존 클래스 목록을 지우고, 파싱된 클래스들의 체크박스를 새로 생성한다.
        Start Class 콤보박스도 함께 업데이트된다.

        Args:
            count: 파싱된 파일 수
            mode_name: 사용된 파서 모드 이름 ("Regex" 또는 "libclang")
        """
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
        """
        검색어 변경 시 클래스 목록을 필터링한다.

        검색어를 포함하는 클래스만 표시하고, 나머지는 숨긴다.
        대소문자를 구분하지 않는다.

        Args:
            *args: Tkinter trace 콜백 인자 (사용되지 않음)
        """
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

    def _get_filter_options(self):
        """
        현재 선택된 필터 옵션을 반환한다.

        체크박스 선택 상태를 분석하여 관계 유형 필터와
        클래스 구성요소 표시 옵션을 결정한다.

        필터 로직:
            - 아무것도 선택 안 함 → 전체 적용
            - 모두 선택 → 전체 적용
            - 일부만 선택 → 선택된 것만 적용

        Returns:
            tuple: (relationship_types, component_options)
                - relationship_types: 관계 유형 리스트 또는 None (전체)
                  예: ['inheritance', 'composition'] 또는 None
                - component_options: 구성요소 표시 딕셔너리
                  예: {'members': True, 'methods': False}
        """
        # Relationship types
        rel_checked = [k for k, v in self.rel_filter_vars.items() if v.get()]
        if len(rel_checked) == 0 or len(rel_checked) == len(self.rel_filter_vars):
            rel_types = None  # All types
        else:
            rel_types = rel_checked

        # Component options
        comp_checked = [k for k, v in self.component_filter_vars.items() if v.get()]
        if len(comp_checked) == 0 or len(comp_checked) == len(self.component_filter_vars):
            comp_options = {"members": True, "methods": True}
        else:
            comp_options = {
                "members": "members" in comp_checked,
                "methods": "methods" in comp_checked
            }

        return rel_types, comp_options

    def _select_all(self):
        """클래스 목록의 모든 체크박스를 선택한다."""
        for var in self.class_vars.values():
            var.set(True)

    def _select_none(self):
        """클래스 목록의 모든 체크박스를 해제한다."""
        for var in self.class_vars.values():
            var.set(False)

    def _generate_diagram(self):
        """
        시작 클래스 기준으로 다이어그램을 생성한다.

        선택된 시작 클래스에서 지정된 Depth만큼 관계를 탐색하여
        PlantUML 클래스 다이어그램을 생성한다.

        동작 과정:
            1. 필터 옵션 확인 (관계 유형, 구성요소 표시)
            2. RelationshipAnalyzer로 관계 분석 (BFS)
            3. PlantUMLGenerator로 코드 생성
            4. 출력 영역에 결과 표시
            5. Image 모드인 경우 이미지 새로고침

        Raises:
            messagebox.showerror: 프로젝트가 파싱되지 않았거나
                                  시작 클래스가 유효하지 않은 경우
        """
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
            # Get filter options
            rel_types, comp_options = self._get_filter_options()

            plantuml = self.generator.generate_from_class(
                start_class, depth,
                rel_type_filter=rel_types,
                component_options=comp_options
            )
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
        """
        선택된 모든 클래스에 대한 다이어그램을 생성한다.

        좌측 클래스 목록에서 체크된 클래스들만 포함하여
        PlantUML 다이어그램을 생성한다. Depth 탐색 없이
        선택된 클래스 간의 관계만 표시한다.

        동작 과정:
            1. 체크된 클래스 목록 수집
            2. 필터 옵션 확인
            3. 선택된 클래스들 간의 관계만 분석
            4. PlantUML 코드 생성 및 표시

        Raises:
            messagebox.showerror: 프로젝트가 파싱되지 않았거나
                                  선택된 클래스가 없는 경우
        """
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
            # Get filter options
            rel_types, comp_options = self._get_filter_options()

            # Convert rel_types to RelationType enum for filtering
            from relationship import RelationType
            allowed_types = None
            if rel_types:
                type_map = {
                    'inheritance': RelationType.INHERITANCE,
                    'composition': RelationType.COMPOSITION,
                    'aggregation': RelationType.AGGREGATION,
                    'dependency': RelationType.DEPENDENCY
                }
                allowed_types = {type_map[t] for t in rel_types if t in type_map}

            analyzer = RelationshipAnalyzer(self.parser)

            # Get relationships only for selected classes
            all_rels = []
            for class_name in selected:
                if class_name in self.parser.classes:
                    class_info = self.parser.classes[class_name]
                    rels = analyzer._analyze_class(class_info)
                    # Filter to only include relationships between selected classes
                    for rel in rels:
                        # Filter by relationship type
                        if allowed_types and rel.rel_type not in allowed_types:
                            continue
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

            plantuml = self.generator.generate(
                set(selected), unique_rels, "Selected Classes Diagram", comp_options)
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
        """
        현재 PlantUML 코드를 클립보드에 복사한다.

        출력 영역의 텍스트를 시스템 클립보드에 복사하여
        다른 프로그램에서 붙여넣기할 수 있도록 한다.
        """
        content = self.output_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("Warning", "No content to copy.")
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.status_var.set("Copied to clipboard")

    def _save_to_file(self):
        """
        현재 PlantUML 코드를 파일로 저장한다.

        파일 저장 다이얼로그를 열어 사용자가 저장 위치와
        파일명을 지정할 수 있도록 한다.
        기본 확장자는 .puml이다.
        """
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
        """
        PlantUML 온라인 서버에서 다이어그램을 미리본다.

        현재 PlantUML 코드를 URL 인코딩하여
        plantuml.com 서버에서 렌더링된 결과를 브라우저로 연다.

        Note:
            URL 길이가 8000자를 초과하면 온라인 미리보기가
            불가능하므로 로컬 PlantUML 사용을 권장한다.
        """
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
        """
        줄 번호 위젯을 업데이트한다.

        출력 텍스트의 줄 수에 맞게 줄 번호를 생성하여 표시한다.
        텍스트 변경이나 스크롤 시 호출된다.

        Args:
            event: 이벤트 객체 (선택적, 이벤트 바인딩용)
        """
        self.line_numbers.configure(state=tk.NORMAL)
        self.line_numbers.delete("1.0", tk.END)

        # Get number of lines
        line_count = int(self.output_text.index('end-1c').split('.')[0])

        # Generate line numbers
        line_numbers_text = "\n".join(str(i) for i in range(1, line_count + 1))
        self.line_numbers.insert("1.0", line_numbers_text)

        self.line_numbers.configure(state=tk.DISABLED)

    def _sync_scroll(self, *args):
        """
        줄 번호와 텍스트 영역의 스크롤을 동기화한다.

        Args:
            *args: 스크롤바 명령 인자
        """
        self.output_text.yview(*args)
        self.line_numbers.yview(*args)

    def _on_text_scroll(self, scrollbar, *args):
        """
        텍스트 스크롤 시 줄 번호 위젯도 함께 스크롤한다.

        Args:
            scrollbar: 스크롤바 위젯
            *args: 스크롤 위치 인자
        """
        scrollbar.set(*args)
        self.line_numbers.yview_moveto(args[0])

    def _toggle_view(self):
        """
        Text/Image 뷰 모드를 전환한다.

        Text 모드: PlantUML 코드를 텍스트로 표시
        Image 모드: PlantUML 서버에서 렌더링된 이미지 표시

        Image 모드 전환 시 Pillow가 설치되어 있지 않으면
        경고 메시지를 표시하고 Text 모드로 유지한다.
        """
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
        """
        PlantUML 텍스트를 서버 URL용으로 인코딩한다.

        PlantUML 서버가 요구하는 형식으로 텍스트를 압축하고
        커스텀 Base64 인코딩을 적용한다.

        인코딩 과정:
            1. UTF-8로 인코딩
            2. zlib으로 압축 (레벨 9)
            3. PlantUML 전용 Base64 변환

        Args:
            text: 인코딩할 PlantUML 코드

        Returns:
            str: 인코딩된 문자열 (URL에 사용 가능)
        """
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
        """
        PlantUML 서버에서 다이어그램 이미지를 가져와 표시한다.

        현재 PlantUML 코드를 인코딩하여 서버에 요청하고,
        받은 PNG 이미지를 캔버스에 표시한다.
        네트워크 요청은 별도 스레드에서 수행된다.

        이미지 로드 과정:
            1. PlantUML 코드 인코딩
            2. 서버에 HTTP 요청 (PNG 형식)
            3. PIL로 이미지 로드
            4. Tkinter PhotoImage로 변환
            5. 캔버스에 표시
        """
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
        """
        가져온 이미지를 캔버스에 표시한다.

        Args:
            width: 이미지 너비 (픽셀)
            height: 이미지 높이 (픽셀)
        """
        self.image_canvas.delete("all")
        self.image_canvas.create_image(0, 0, anchor=tk.NW, image=self.current_image)
        self.image_canvas.configure(scrollregion=(0, 0, width, height))
        self.status_var.set("Diagram image loaded")


def main():
    """
    애플리케이션 진입점.

    Tkinter root 윈도우를 생성하고 Cpp2PlantUMLApp 인스턴스를
    초기화한 후 메인 이벤트 루프를 시작한다.
    """
    root = tk.Tk()
    app = Cpp2PlantUMLApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
