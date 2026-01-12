"""
PlantUML Generator
Generates PlantUML class diagram code from parsed C++ classes
"""

from typing import List, Set, Dict
from cpp_parser import ClassInfo, CppParser
from relationship import Relationship, RelationType


class PlantUMLGenerator:
    """
    PlantUML 클래스 다이어그램 코드 생성기.

    파싱된 C++ 클래스 정보와 관계를 PlantUML 형식의
    텍스트 코드로 변환한다.

    Class Attributes:
        ACCESS_SYMBOLS: 접근 제어자별 PlantUML 기호 매핑
            - public: +
            - private: -
            - protected: #
        RELATIONSHIP_ARROWS: 관계 유형별 PlantUML 화살표 매핑
            - INHERITANCE: <|--
            - COMPOSITION: *--
            - AGGREGATION: o--
            - DEPENDENCY: ..>

    Attributes:
        parser: C++ 파서 인스턴스
    """

    # Access specifier symbols
    ACCESS_SYMBOLS = {
        "public": "+",
        "private": "-",
        "protected": "#"
    }

    # Relationship arrows
    RELATIONSHIP_ARROWS = {
        RelationType.INHERITANCE: "<|--",
        RelationType.COMPOSITION: "*--",
        RelationType.AGGREGATION: "o--",
        RelationType.DEPENDENCY: "..>"
    }

    def __init__(self, parser: CppParser):
        """
        PlantUML 생성기를 초기화한다.

        Args:
            parser: 클래스 정보가 파싱된 CppParser 인스턴스
        """
        self.parser = parser

    def _format_type(self, type_str: str) -> str:
        """
        타입 문자열을 PlantUML 형식에 맞게 변환한다.

        PlantUML에서 특수 문자로 사용되는 < >를 ~로 대체한다.

        Args:
            type_str: 원본 타입 문자열

        Returns:
            str: PlantUML용으로 이스케이프된 타입 문자열
        """
        # Escape special characters
        type_str = type_str.replace("<", "~").replace(">", "~")
        return type_str

    def _generate_class(self, class_info: ClassInfo,
                        show_members: bool = True, show_methods: bool = True) -> str:
        """
        단일 클래스의 PlantUML 코드를 생성한다.

        클래스 이름, 멤버 변수, 메서드를 PlantUML 형식으로 포맷팅한다.
        접근 제어자별로 그룹화하여 출력한다.

        출력 형식:
            class ClassName {
                +publicMember: Type
                -privateMember: Type
                --
                +publicMethod(): ReturnType
                -privateMethod(): ReturnType
            }

        Args:
            class_info: 클래스 정보 객체
            show_members: 멤버 변수 표시 여부
            show_methods: 메서드 표시 여부

        Returns:
            str: PlantUML 클래스 정의 코드
        """
        lines = []

        # Class declaration
        keyword = "class"
        if class_info.is_struct:
            keyword = "class"  # PlantUML doesn't distinguish struct

        lines.append(f"{keyword} {class_info.name} {{")

        # Group by access specifier
        members_by_access: Dict[str, List[str]] = {
            "public": [],
            "protected": [],
            "private": []
        }
        methods_by_access: Dict[str, List[str]] = {
            "public": [],
            "protected": [],
            "private": []
        }

        # Format members (if enabled)
        if show_members:
            for member in class_info.members:
                symbol = self.ACCESS_SYMBOLS.get(member.access, "-")
                type_str = self._format_type(member.type_name)
                members_by_access[member.access].append(
                    f"  {symbol}{member.name}: {type_str}"
                )

        # Format methods (if enabled)
        if show_methods:
            for method in class_info.methods:
                symbol = self.ACCESS_SYMBOLS.get(method.access, "-")

                # Format parameters
                params = []
                for pname, ptype in method.parameters:
                    ptype_str = self._format_type(ptype)
                    if pname:
                        params.append(f"{pname}: {ptype_str}")
                    else:
                        params.append(ptype_str)
                params_str = ", ".join(params)

                # Format return type
                if method.return_type:
                    ret_str = self._format_type(method.return_type)
                    methods_by_access[method.access].append(
                        f"  {symbol}{method.name}({params_str}): {ret_str}"
                    )
                else:
                    # Constructor/Destructor
                    methods_by_access[method.access].append(
                        f"  {symbol}{method.name}({params_str})"
                    )

        # Output in order: public, protected, private
        for access in ["public", "protected", "private"]:
            for member_line in members_by_access[access]:
                lines.append(member_line)

        # Separator between members and methods if both exist
        has_members = any(members_by_access[a] for a in members_by_access)
        has_methods = any(methods_by_access[a] for a in methods_by_access)
        if has_members and has_methods:
            lines.append("  --")

        for access in ["public", "protected", "private"]:
            for method_line in methods_by_access[access]:
                lines.append(method_line)

        lines.append("}")
        return "\n".join(lines)

    def _generate_relationship(self, rel: Relationship) -> str:
        """
        관계의 PlantUML 코드를 생성한다.

        관계 유형에 맞는 화살표를 사용하여 두 클래스 간
        연결을 표현하는 코드를 생성한다.

        Args:
            rel: Relationship 객체

        Returns:
            str: PlantUML 관계 코드 (예: "ClassA <|-- ClassB")
        """
        arrow = self.RELATIONSHIP_ARROWS.get(rel.rel_type, "-->")

        if rel.label:
            return f"{rel.from_class} {arrow} {rel.to_class} : {rel.label}"
        else:
            return f"{rel.from_class} {arrow} {rel.to_class}"

    def generate(self, class_names: Set[str], relationships: List[Relationship],
                 title: str = None, component_options: dict = None) -> str:
        """
        완전한 PlantUML 다이어그램 코드를 생성한다.

        @startuml/@enduml을 포함한 완전한 PlantUML 코드를 생성한다.
        클래스 정의와 관계를 모두 포함한다.

        생성 순서:
            1. @startuml, 제목, 스타일 설정
            2. 클래스 정의 (알파벳 순)
            3. 관계 정의
            4. @enduml

        Args:
            class_names: 포함할 클래스 이름 집합
            relationships: 클래스 간 관계 목록
            title: 다이어그램 제목 (선택적)
            component_options: 구성요소 표시 옵션
                - 'members': 멤버 변수 표시 여부 (bool)
                - 'methods': 메서드 표시 여부 (bool)

        Returns:
            str: 완전한 PlantUML 코드
        """
        # Default options
        show_members = True
        show_methods = True
        if component_options:
            show_members = component_options.get('members', True)
            show_methods = component_options.get('methods', True)

        lines = ["@startuml"]

        # Add title if provided
        if title:
            lines.append(f"title {title}")
            lines.append("")

        # Styling
        lines.append("skinparam classAttributeIconSize 0")
        lines.append("skinparam classFontStyle bold")
        lines.append("")

        # Generate class definitions
        for class_name in sorted(class_names):
            if class_name in self.parser.classes:
                class_info = self.parser.classes[class_name]
                lines.append(self._generate_class(class_info, show_members, show_methods))
                lines.append("")

        # Generate relationships
        if relationships:
            lines.append("' Relationships")
            for rel in relationships:
                lines.append(self._generate_relationship(rel))

        lines.append("@enduml")
        return "\n".join(lines)

    def generate_from_class(self, start_class: str, max_depth: int = 3,
                            title: str = None, rel_type_filter: list = None,
                            component_options: dict = None) -> str:
        """
        시작 클래스 기준으로 PlantUML 코드를 생성한다.

        RelationshipAnalyzer를 사용하여 시작 클래스에서
        지정된 깊이까지 관계를 분석하고 다이어그램을 생성한다.

        Args:
            start_class: 시작 클래스 이름
            max_depth: 최대 탐색 깊이 (기본값: 3)
            title: 다이어그램 제목 (선택적, 미지정 시 자동 생성)
            rel_type_filter: 포함할 관계 유형 목록 (None이면 전체)
                            예: ['inheritance', 'composition']
            component_options: 구성요소 표시 옵션
                - 'members': 멤버 변수 표시 여부
                - 'methods': 메서드 표시 여부

        Returns:
            str: 완전한 PlantUML 코드
        """
        from relationship import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer(self.parser)
        classes, relationships = analyzer.analyze_from_class(
            start_class, max_depth, rel_type_filter)

        if not title:
            title = f"Class Diagram: {start_class} (depth={max_depth})"

        return self.generate(classes, relationships, title, component_options)

    def generate_all(self, title: str = None) -> str:
        """
        모든 클래스에 대한 PlantUML 코드를 생성한다.

        파싱된 모든 클래스와 그들 간의 관계를 포함하는
        전체 다이어그램을 생성한다.

        Args:
            title: 다이어그램 제목 (선택적)

        Returns:
            str: 완전한 PlantUML 코드
        """
        from relationship import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer(self.parser)
        classes, relationships = analyzer.analyze_all()

        if not title:
            title = "Full Class Diagram"

        return self.generate(classes, relationships, title)
