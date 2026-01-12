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
    """
    C++ 메서드 정보를 저장하는 데이터 클래스.

    Attributes:
        name: 메서드 이름 (생성자/소멸자 포함)
        return_type: 반환 타입 (생성자/소멸자는 빈 문자열)
        parameters: 매개변수 리스트 [(이름, 타입), ...]
        access: 접근 제어자 ('public', 'private', 'protected')
    """
    name: str
    return_type: str
    parameters: List[tuple]  # [(name, type), ...]
    access: str  # public, private, protected


@dataclass
class MemberInfo:
    """
    C++ 멤버 변수 정보를 저장하는 데이터 클래스.

    Attributes:
        name: 멤버 변수 이름
        type_name: 변수 타입
        access: 접근 제어자 ('public', 'private', 'protected')
    """
    name: str
    type_name: str
    access: str  # public, private, protected


@dataclass
class ClassInfo:
    """
    C++ 클래스/구조체 정보를 저장하는 데이터 클래스.

    Attributes:
        name: 클래스/구조체 이름
        members: 멤버 변수 목록
        methods: 메서드 목록
        base_classes: 상속받은 부모 클래스 이름 목록
        file_path: 클래스가 정의된 파일 경로
        is_struct: 구조체 여부 (True면 struct, False면 class)
    """
    name: str
    members: List[MemberInfo] = field(default_factory=list)
    methods: List[MethodInfo] = field(default_factory=list)
    base_classes: List[str] = field(default_factory=list)
    file_path: str = ""
    is_struct: bool = False


class CppParser:
    """
    정규 표현식 기반 C++ 파서.

    libclang 없이 정규 표현식만으로 C++ 소스 코드를 분석한다.
    완벽한 파싱은 아니지만 대부분의 일반적인 클래스 구조를 추출할 수 있다.

    Attributes:
        classes: 파싱된 클래스 정보 딕셔너리 {클래스명: ClassInfo}
        parsed_files: 이미 파싱된 파일 경로 집합

    Note:
        복잡한 템플릿이나 매크로는 제대로 파싱되지 않을 수 있다.
    """

    def __init__(self, libclang_path: Optional[str] = None):
        """
        파서를 초기화한다.

        Args:
            libclang_path: 무시됨 (CppParserClang과의 인터페이스 호환성 유지용)
        """
        self.classes: Dict[str, ClassInfo] = {}
        self.parsed_files: Set[str] = set()

    def _remove_comments(self, content: str) -> str:
        """
        소스 코드에서 C/C++ 주석을 제거한다.

        Args:
            content: 원본 소스 코드

        Returns:
            str: 주석이 제거된 소스 코드
        """
        # Remove single-line comments
        content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
        # Remove multi-line comments
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        return content

    def _remove_preprocessor(self, content: str) -> str:
        """
        전처리기 지시문(#include, #define 등)을 제거한다.

        Args:
            content: 소스 코드

        Returns:
            str: 전처리기 지시문이 제거된 소스 코드
        """
        return re.sub(r'^\s*#.*$', '', content, flags=re.MULTILINE)

    def _find_matching_brace(self, content: str, start: int) -> int:
        """
        여는 중괄호에 대응하는 닫는 중괄호 위치를 찾는다.

        Args:
            content: 소스 코드 문자열
            start: 여는 중괄호의 인덱스

        Returns:
            int: 대응하는 닫는 중괄호의 인덱스, 찾지 못하면 -1
        """
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
        """
        메서드 매개변수 문자열을 파싱한다.

        템플릿 인자 내의 쉼표를 고려하여 매개변수를 분리한다.

        Args:
            params_str: 괄호 안의 매개변수 문자열

        Returns:
            List[tuple]: [(매개변수명, 타입), ...] 리스트
        """
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
        """
        단일 매개변수를 (이름, 타입) 튜플로 파싱한다.

        기본값이 있는 경우 제거하고, 타입과 이름을 분리한다.

        Args:
            param: 단일 매개변수 문자열 (예: "const std::string& name = \"\"")

        Returns:
            tuple: (매개변수명, 타입), 이름이 없으면 ("", 타입)
        """
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
        """
        클래스 본문을 파싱하여 멤버와 메서드를 추출한다.

        접근 제어자(public/private/protected)를 추적하며
        각 줄을 분석하여 멤버 변수와 메서드를 구분한다.

        Args:
            body: 중괄호 내부의 클래스 본문 문자열
            is_struct: struct인 경우 True (기본 접근제어자가 public)

        Returns:
            tuple: (멤버 변수 리스트, 메서드 리스트)
        """
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
        """
        상속 선언을 파싱하여 부모 클래스 목록을 추출한다.

        접근 제어자(public/private/protected)와 virtual 키워드를
        제거하고 순수 클래스 이름만 추출한다.

        Args:
            inheritance_str: 콜론(:) 이후의 상속 선언 문자열
                            예: "public Base1, protected Base2"

        Returns:
            List[str]: 부모 클래스 이름 목록
        """
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
        """
        파싱된 모든 클래스 정보를 반환한다.

        Returns:
            Dict[str, ClassInfo]: {클래스명: ClassInfo} 딕셔너리
        """
        return self.classes

    def get_class(self, name: str) -> Optional[ClassInfo]:
        """
        이름으로 특정 클래스 정보를 조회한다.

        Args:
            name: 조회할 클래스 이름

        Returns:
            Optional[ClassInfo]: 클래스 정보, 없으면 None
        """
        return self.classes.get(name)

    def get_class_names(self) -> List[str]:
        """
        파싱된 모든 클래스 이름 목록을 반환한다.

        Returns:
            List[str]: 클래스 이름 리스트
        """
        return list(self.classes.keys())

    def clear(self):
        """
        파싱된 모든 데이터를 초기화한다.

        classes와 parsed_files를 비워서
        새로운 파싱을 준비한다.
        """
        self.classes.clear()
        self.parsed_files.clear()
