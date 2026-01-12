"""
C++ Parser using libclang
Extracts classes, structs, members, methods, and inheritance relationships
Requires: pip install clang + LLVM/Clang installed
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from pathlib import Path

# Try to import clang
try:
    import clang.cindex as ci
    HAS_CLANG = True
except ImportError:
    HAS_CLANG = False
    ci = None


@dataclass
class MethodInfo:
    name: str
    return_type: str
    parameters: List[tuple]  # [(name, type), ...]
    access: str  # public, private, protected


@dataclass
class MemberInfo:
    name: str
    type_name: str
    access: str  # public, private, protected


@dataclass
class ClassInfo:
    name: str
    members: List[MemberInfo] = field(default_factory=list)
    methods: List[MethodInfo] = field(default_factory=list)
    base_classes: List[str] = field(default_factory=list)
    file_path: str = ""
    is_struct: bool = False


class CppParserClang:
    def __init__(self, libclang_path: Optional[str] = None):
        """
        Initialize the C++ parser using libclang.

        Args:
            libclang_path: Path to libclang.dll/libclang.so (optional)
        """
        if not HAS_CLANG:
            raise ImportError("clang module not found. Install with: pip install clang")

        if libclang_path:
            ci.Config.set_library_file(libclang_path)

        self.index = ci.Index.create()
        self.classes: Dict[str, ClassInfo] = {}
        self.parsed_files: Set[str] = set()

    def _get_access_specifier(self, cursor) -> str:
        """Convert clang access specifier to string."""
        access = cursor.access_specifier
        if access == ci.AccessSpecifier.PUBLIC:
            return "public"
        elif access == ci.AccessSpecifier.PRIVATE:
            return "private"
        elif access == ci.AccessSpecifier.PROTECTED:
            return "protected"
        return "private"  # default for class

    def _get_type_name(self, type_obj) -> str:
        """Get clean type name from clang type."""
        spelling = type_obj.spelling
        # Clean up common patterns
        spelling = spelling.replace("class ", "").replace("struct ", "")
        return spelling

    def _parse_class(self, cursor, file_path: str) -> Optional[ClassInfo]:
        """Parse a class or struct declaration."""
        class_name = cursor.spelling
        if not class_name:
            return None

        is_struct = cursor.kind == ci.CursorKind.STRUCT_DECL
        class_info = ClassInfo(
            name=class_name,
            file_path=file_path,
            is_struct=is_struct
        )

        # Default access: public for struct, private for class
        current_access = "public" if is_struct else "private"

        for child in cursor.get_children():
            # Access specifier change
            if child.kind == ci.CursorKind.CXX_ACCESS_SPEC_DECL:
                current_access = self._get_access_specifier(child)

            # Base class
            elif child.kind == ci.CursorKind.CXX_BASE_SPECIFIER:
                base_name = child.type.spelling
                base_name = base_name.replace("class ", "").replace("struct ", "")
                class_info.base_classes.append(base_name)

            # Member variable
            elif child.kind == ci.CursorKind.FIELD_DECL:
                member = MemberInfo(
                    name=child.spelling,
                    type_name=self._get_type_name(child.type),
                    access=current_access
                )
                class_info.members.append(member)

            # Method
            elif child.kind == ci.CursorKind.CXX_METHOD:
                params = []
                for param in child.get_arguments():
                    params.append((param.spelling, self._get_type_name(param.type)))

                method = MethodInfo(
                    name=child.spelling,
                    return_type=self._get_type_name(child.result_type),
                    parameters=params,
                    access=current_access
                )
                class_info.methods.append(method)

            # Constructor
            elif child.kind == ci.CursorKind.CONSTRUCTOR:
                params = []
                for param in child.get_arguments():
                    params.append((param.spelling, self._get_type_name(param.type)))

                method = MethodInfo(
                    name=child.spelling,
                    return_type="",
                    parameters=params,
                    access=current_access
                )
                class_info.methods.append(method)

            # Destructor
            elif child.kind == ci.CursorKind.DESTRUCTOR:
                method = MethodInfo(
                    name=child.spelling,
                    return_type="",
                    parameters=[],
                    access=current_access
                )
                class_info.methods.append(method)

        return class_info

    def _traverse(self, cursor, file_path: str):
        """Recursively traverse the AST."""
        # Only process if in the target file
        if cursor.location.file:
            cursor_file = str(Path(cursor.location.file.name).resolve())
            target_file = str(Path(file_path).resolve())
            if cursor_file != target_file:
                return

        if cursor.kind in (ci.CursorKind.CLASS_DECL, ci.CursorKind.STRUCT_DECL):
            # Only process definitions, not forward declarations
            if cursor.is_definition():
                class_info = self._parse_class(cursor, file_path)
                if class_info and class_info.name:
                    self.classes[class_info.name] = class_info

        for child in cursor.get_children():
            self._traverse(child, file_path)

    def parse_file(self, file_path: str, include_paths: List[str] = None) -> bool:
        """
        Parse a single C++ file.

        Args:
            file_path: Path to the C++ file
            include_paths: Additional include directories

        Returns:
            True if parsing was successful
        """
        file_path = str(Path(file_path).resolve())
        if file_path in self.parsed_files:
            return True

        args = ['-x', 'c++', '-std=c++17']
        if include_paths:
            for inc in include_paths:
                args.append(f'-I{inc}')

        try:
            tu = self.index.parse(file_path, args=args)

            # Check for fatal errors
            has_fatal = False
            for diag in tu.diagnostics:
                if diag.severity >= ci.Diagnostic.Error:
                    has_fatal = True
                    break

            self._traverse(tu.cursor, file_path)
            self.parsed_files.add(file_path)
            return not has_fatal

        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            return False

    def parse_directory(self, dir_path: str, extensions: List[str] = None,
                        include_paths: List[str] = None) -> int:
        """
        Parse all C++ files in a directory.

        Args:
            dir_path: Path to the directory
            extensions: File extensions to parse (default: ['.h', '.hpp', '.cpp', '.cc'])
            include_paths: Additional include directories

        Returns:
            Number of files parsed
        """
        if extensions is None:
            extensions = ['.h', '.hpp', '.hxx', '.cpp', '.cc', '.cxx']

        dir_path = Path(dir_path)
        if include_paths is None:
            include_paths = [str(dir_path)]
        else:
            include_paths = [str(dir_path)] + include_paths

        count = 0
        for ext in extensions:
            for file_path in dir_path.rglob(f'*{ext}'):
                if self.parse_file(str(file_path), include_paths):
                    count += 1

        return count

    def get_classes(self) -> Dict[str, ClassInfo]:
        """Get all parsed classes."""
        return self.classes

    def get_class(self, name: str) -> Optional[ClassInfo]:
        """Get a specific class by name."""
        return self.classes.get(name)

    def get_class_names(self) -> List[str]:
        """Get list of all class names."""
        return list(self.classes.keys())

    def clear(self):
        """Clear all parsed data."""
        self.classes.clear()
        self.parsed_files.clear()


def is_available() -> bool:
    """Check if libclang is available."""
    return HAS_CLANG
