"""
C++ Parser using Regular Expressions
Extracts classes, structs, members, methods, and inheritance relationships
No external dependencies required!
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from pathlib import Path


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


class CppParser:
    def __init__(self, libclang_path: Optional[str] = None):
        """
        Initialize the C++ parser.
        libclang_path is ignored (kept for compatibility).
        """
        self.classes: Dict[str, ClassInfo] = {}
        self.parsed_files: Set[str] = set()

    def _remove_comments(self, content: str) -> str:
        """Remove C/C++ comments from source code."""
        # Remove single-line comments
        content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
        # Remove multi-line comments
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        return content

    def _remove_preprocessor(self, content: str) -> str:
        """Remove preprocessor directives."""
        return re.sub(r'^\s*#.*$', '', content, flags=re.MULTILINE)

    def _find_matching_brace(self, content: str, start: int) -> int:
        """Find the matching closing brace."""
        count = 0
        i = start
        while i < len(content):
            if content[i] == '{':
                count += 1
            elif content[i] == '}':
                count -= 1
                if count == 0:
                    return i
            i += 1
        return -1

    def _parse_parameters(self, params_str: str) -> List[tuple]:
        """Parse method parameters."""
        params = []
        if not params_str.strip():
            return params

        # Split by comma, but be careful with templates
        depth = 0
        current = ""
        for char in params_str:
            if char in '<(':
                depth += 1
            elif char in '>)':
                depth -= 1
            elif char == ',' and depth == 0:
                if current.strip():
                    params.append(self._parse_single_param(current.strip()))
                current = ""
                continue
            current += char

        if current.strip():
            params.append(self._parse_single_param(current.strip()))

        return params

    def _parse_single_param(self, param: str) -> tuple:
        """Parse a single parameter into (name, type)."""
        # Remove default values
        param = re.sub(r'\s*=\s*[^,)]+', '', param)
        param = param.strip()

        # Try to split type and name
        # Handle cases like "const std::string& name" or "int x"
        match = re.match(r'^(.+?)(\s+|\s*[&*]+\s*)(\w+)$', param)
        if match:
            type_part = match.group(1) + match.group(2).replace(' ', '')
            name_part = match.group(3)
            return (name_part.strip(), type_part.strip())

        # If no name found, it's just a type
        return ("", param)

    def _parse_class_body(self, body: str, is_struct: bool) -> tuple:
        """Parse class body to extract members and methods."""
        members = []
        methods = []

        # Default access
        current_access = "public" if is_struct else "private"

        # Split by lines and process
        lines = body.split('\n')
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            # Skip empty lines
            if not line:
                i += 1
                continue

            # Check for access specifier
            access_match = re.match(r'^(public|private|protected)\s*:', line)
            if access_match:
                current_access = access_match.group(1)
                i += 1
                continue

            # Check for method (has parentheses)
            # Pattern: [virtual] [static] return_type name(params) [const] [override] [= 0];
            method_match = re.match(
                r'^(?:virtual\s+)?(?:static\s+)?(?:inline\s+)?'
                r'([\w:&*<>,\s]+?)\s+'  # return type
                r'(~?\w+)\s*'  # method name (including destructor ~)
                r'\(([^)]*)\)\s*'  # parameters
                r'(?:const\s*)?(?:override\s*)?(?:final\s*)?'
                r'(?:=\s*(?:0|default|delete)\s*)?;',
                line
            )

            if method_match:
                ret_type = method_match.group(1).strip()
                name = method_match.group(2).strip()
                params_str = method_match.group(3).strip()

                # Skip if it looks like a variable declaration
                if ret_type and name and '(' not in ret_type:
                    params = self._parse_parameters(params_str)
                    methods.append(MethodInfo(
                        name=name,
                        return_type=ret_type,
                        parameters=params,
                        access=current_access
                    ))
                    i += 1
                    continue

            # Check for constructor/destructor
            ctor_match = re.match(
                r'^(~?\w+)\s*\(([^)]*)\)\s*(?::\s*[^{;]+)?(?:;|{)',
                line
            )
            if ctor_match:
                name = ctor_match.group(1).strip()
                params_str = ctor_match.group(2).strip()
                params = self._parse_parameters(params_str)
                methods.append(MethodInfo(
                    name=name,
                    return_type="",
                    parameters=params,
                    access=current_access
                ))
                i += 1
                continue

            # Check for member variable
            # Pattern: [static] [const] type name [= value];
            member_match = re.match(
                r'^(?:static\s+)?(?:const\s+)?(?:mutable\s+)?'
                r'([\w:&*<>,\s]+?)\s+'  # type
                r'(\w+)\s*'  # name
                r'(?:\[[^\]]*\])?\s*'  # optional array
                r'(?:=\s*[^;]+)?;',  # optional initializer
                line
            )

            if member_match:
                type_name = member_match.group(1).strip()
                name = member_match.group(2).strip()

                # Skip if it looks like a method or keyword
                if type_name and name and type_name not in ['return', 'if', 'else', 'for', 'while']:
                    members.append(MemberInfo(
                        name=name,
                        type_name=type_name,
                        access=current_access
                    ))

            i += 1

        return members, methods

    def _parse_inheritance(self, inheritance_str: str) -> List[str]:
        """Parse inheritance declaration."""
        bases = []
        if not inheritance_str:
            return bases

        # Split by comma
        parts = inheritance_str.split(',')
        for part in parts:
            # Remove access specifier and extract class name
            part = re.sub(r'\b(public|private|protected|virtual)\b', '', part)
            part = part.strip()
            if part:
                bases.append(part)

        return bases

    def parse_file(self, file_path: str, include_paths: List[str] = None) -> bool:
        """
        Parse a single C++ file.

        Args:
            file_path: Path to the C++ file
            include_paths: Ignored (kept for compatibility)

        Returns:
            True if parsing was successful
        """
        file_path = str(Path(file_path).resolve())
        if file_path in self.parsed_files:
            return True

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return False

        # Preprocess
        content = self._remove_comments(content)
        content = self._remove_preprocessor(content)

        # Find class/struct declarations
        # Pattern: class/struct Name [: inheritance] {
        pattern = r'\b(class|struct)\s+(\w+)\s*(?::\s*([^{]+))?\s*\{'

        for match in re.finditer(pattern, content):
            keyword = match.group(1)
            class_name = match.group(2)
            inheritance = match.group(3)

            is_struct = keyword == 'struct'

            # Find class body
            start_brace = match.end() - 1
            end_brace = self._find_matching_brace(content, start_brace)

            if end_brace == -1:
                continue

            body = content[start_brace + 1:end_brace]

            # Parse body
            members, methods = self._parse_class_body(body, is_struct)

            # Parse inheritance
            base_classes = self._parse_inheritance(inheritance) if inheritance else []

            # Create ClassInfo
            class_info = ClassInfo(
                name=class_name,
                members=members,
                methods=methods,
                base_classes=base_classes,
                file_path=file_path,
                is_struct=is_struct
            )

            self.classes[class_name] = class_info

        self.parsed_files.add(file_path)
        return True

    def parse_directory(self, dir_path: str, extensions: List[str] = None,
                        include_paths: List[str] = None) -> int:
        """
        Parse all C++ files in a directory.

        Args:
            dir_path: Path to the directory
            extensions: File extensions to parse (default: ['.h', '.hpp', '.cpp', '.cc'])
            include_paths: Ignored (kept for compatibility)

        Returns:
            Number of files parsed
        """
        if extensions is None:
            extensions = ['.h', '.hpp', '.hxx', '.cpp', '.cc', '.cxx']

        dir_path = Path(dir_path)
        count = 0

        for ext in extensions:
            for file_path in dir_path.rglob(f'*{ext}'):
                if self.parse_file(str(file_path)):
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
