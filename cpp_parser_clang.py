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


class CppParserClang:
    """
    libclang 기반 C++ 파서.

    LLVM/Clang의 libclang을 사용하여 정확한 AST(Abstract Syntax Tree)
    기반 파싱을 수행한다. 정규 표현식 파서보다 정확하지만
    LLVM/Clang 설치가 필요하다.

    Attributes:
        index: clang Index 객체
        classes: 파싱된 클래스 정보 딕셔너리 {클래스명: ClassInfo}
        parsed_files: 이미 파싱된 파일 경로 집합

    Requirements:
        - pip install clang
        - LLVM/Clang 설치 (libclang.dll 또는 libclang.so)
    """

    def __init__(self, libclang_path: Optional[str] = None):
        """
        libclang을 사용하는 파서를 초기화한다.

        Args:
            libclang_path: libclang 라이브러리 경로 (선택적)
                          지정하지 않으면 시스템 기본 경로에서 검색

        Raises:
            ImportError: clang 모듈이 설치되지 않은 경우
        """
        if not HAS_CLANG:
            raise ImportError("clang module not found. Install with: pip install clang")

        if libclang_path:
            ci.Config.set_library_file(libclang_path)

        self.index = ci.Index.create()
        self.classes: Dict[str, ClassInfo] = {}
        self.parsed_files: Set[str] = set()

    def _get_access_specifier(self, cursor) -> str:
        """
        clang 커서의 접근 제어자를 문자열로 변환한다.

        Args:
            cursor: clang Cursor 객체

        Returns:
            str: 'public', 'private', 'protected' 중 하나
        """
        access = cursor.access_specifier
        if access == ci.AccessSpecifier.PUBLIC:
            return "public"
        elif access == ci.AccessSpecifier.PRIVATE:
            return "private"
        elif access == ci.AccessSpecifier.PROTECTED:
            return "protected"
        return "private"  # default for class

    def _get_type_name(self, type_obj) -> str:
        """
        clang 타입 객체에서 정제된 타입 이름을 추출한다.

        'class ' 또는 'struct ' 접두사를 제거하여 순수 타입명만 반환한다.

        Args:
            type_obj: clang Type 객체

        Returns:
            str: 정제된 타입 이름
        """
        spelling = type_obj.spelling
        # Clean up common patterns
        spelling = spelling.replace("class ", "").replace("struct ", "")
        return spelling

    def _parse_class(self, cursor, file_path: str) -> Optional[ClassInfo]:
        """
        클래스 또는 구조체 선언을 파싱한다.

        커서의 자식 노드들을 순회하며 멤버 변수, 메서드,
        생성자, 소멸자, 상속 관계를 추출한다.

        Args:
            cursor: 클래스/구조체 선언의 clang Cursor
            file_path: 소스 파일 경로

        Returns:
            Optional[ClassInfo]: 파싱된 클래스 정보, 이름이 없으면 None
        """
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
        """
        AST를 재귀적으로 순회하며 클래스/구조체를 수집한다.

        대상 파일에 정의된 클래스/구조체만 처리하고,
        전방 선언(forward declaration)은 무시한다.

        Args:
            cursor: 현재 AST 노드의 clang Cursor
            file_path: 파싱 대상 파일 경로
        """
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


def is_available() -> bool:
    """
    libclang 사용 가능 여부를 확인한다.

    clang 모듈이 import 가능한지 확인하여
    libclang 모드 사용 가능 여부를 반환한다.

    Returns:
        bool: libclang 사용 가능하면 True
    """
    return HAS_CLANG
