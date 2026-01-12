"""
Relationship Analyzer
Analyzes class relationships (inheritance, composition, aggregation, dependency)
with depth limiting using BFS
"""

from dataclasses import dataclass
from typing import Dict, Set, List, Optional
from collections import deque
from enum import Enum
import re

from cpp_parser import ClassInfo, CppParser


class RelationType(Enum):
    """
    클래스 간 관계 유형을 정의하는 열거형.

    PlantUML 화살표 표기:
        - INHERITANCE: A <|-- B (B가 A를 상속)
        - COMPOSITION: A *-- B (A가 B를 값으로 포함)
        - AGGREGATION: A o-- B (A가 B를 포인터/참조로 포함)
        - DEPENDENCY: A ..> B (A가 메서드에서 B를 사용)
    """
    INHERITANCE = "inheritance"     # A <|-- B (B inherits A)
    COMPOSITION = "composition"     # A *-- B (A contains B as value)
    AGGREGATION = "aggregation"     # A o-- B (A contains B as pointer/ref)
    DEPENDENCY = "dependency"       # A ..> B (A uses B in method)


@dataclass
class Relationship:
    """
    두 클래스 간의 관계를 표현하는 데이터 클래스.

    Attributes:
        from_class: 관계의 시작 클래스 (화살표 시작점)
        to_class: 관계의 대상 클래스 (화살표 끝점)
        rel_type: 관계 유형 (RelationType)
        label: 관계에 표시할 라벨 (선택적)
    """
    from_class: str
    to_class: str
    rel_type: RelationType
    label: str = ""


class RelationshipAnalyzer:
    """
    클래스 간 관계를 분석하는 클래스.

    파싱된 클래스 정보를 기반으로 상속, 구성, 집합, 의존 관계를
    분석한다. BFS를 사용하여 지정된 깊이까지 관계를 탐색한다.

    Attributes:
        parser: C++ 파서 인스턴스
        relationships: 분석된 관계 목록
    """

    def __init__(self, parser: CppParser):
        """
        관계 분석기를 초기화한다.

        Args:
            parser: 클래스 정보가 파싱된 CppParser 인스턴스
        """
        self.parser = parser
        self.relationships: List[Relationship] = []

    def _extract_type_name(self, type_str: str) -> Optional[str]:
        """
        타입 문자열에서 핵심 클래스 이름을 추출한다.

        const, volatile, 포인터(*), 참조(&), 템플릿, 네임스페이스를
        제거하고 순수 클래스 이름만 반환한다.

        Args:
            type_str: 타입 문자열 (예: "const std::vector<MyClass*>&")

        Returns:
            Optional[str]: 추출된 클래스 이름, 추출 실패 시 None
        """
        # Remove const, volatile
        type_str = re.sub(r'\b(const|volatile)\b', '', type_str).strip()

        # Remove pointer/reference symbols
        type_str = type_str.rstrip('*&').strip()

        # Handle common templates (vector, list, map, etc.)
        template_match = re.match(r'(\w+)<(.+)>', type_str)
        if template_match:
            # Get the inner type
            inner = template_match.group(2)
            # For map-like types, try to get value type
            if ',' in inner:
                parts = inner.split(',')
                inner = parts[-1].strip()
            return self._extract_type_name(inner)

        # Remove scope operator prefixes (std::, etc.)
        if '::' in type_str:
            type_str = type_str.split('::')[-1]

        # Check if it's a known class
        type_str = type_str.strip()
        return type_str if type_str else None

    def _is_pointer_or_reference(self, type_str: str) -> bool:
        """
        타입이 포인터 또는 참조인지 확인한다.

        Args:
            type_str: 타입 문자열

        Returns:
            bool: 포인터(*) 또는 참조(&)로 끝나면 True
        """
        type_str = type_str.strip()
        return type_str.endswith('*') or type_str.endswith('&')

    def _is_known_class(self, type_name: str) -> bool:
        """
        타입 이름이 파싱된 클래스 중 하나인지 확인한다.

        Args:
            type_name: 확인할 타입 이름

        Returns:
            bool: 파싱된 클래스에 존재하면 True
        """
        return type_name in self.parser.classes

    def _analyze_class(self, class_info: ClassInfo) -> List[Relationship]:
        """
        단일 클래스의 관계를 분석한다.

        상속, 멤버 변수(구성/집합), 메서드 매개변수(의존) 관계를 추출한다.

        분석 순서:
            1. 상속 관계 (base_classes에서 추출)
            2. 멤버 변수 관계 (값이면 구성, 포인터/참조면 집합)
            3. 메서드 의존 관계 (매개변수, 반환 타입에서 추출)

        Args:
            class_info: 분석할 클래스 정보

        Returns:
            List[Relationship]: 해당 클래스의 관계 목록
        """
        relationships = []
        class_name = class_info.name

        # Inheritance relationships
        for base in class_info.base_classes:
            base_name = self._extract_type_name(base)
            if base_name:
                relationships.append(Relationship(
                    from_class=base_name,
                    to_class=class_name,
                    rel_type=RelationType.INHERITANCE
                ))

        # Member relationships (composition/aggregation)
        seen_members = set()
        for member in class_info.members:
            type_name = self._extract_type_name(member.type_name)
            if type_name and type_name != class_name and type_name not in seen_members:
                if self._is_known_class(type_name):
                    seen_members.add(type_name)
                    if self._is_pointer_or_reference(member.type_name):
                        rel_type = RelationType.AGGREGATION
                    else:
                        rel_type = RelationType.COMPOSITION
                    relationships.append(Relationship(
                        from_class=class_name,
                        to_class=type_name,
                        rel_type=rel_type
                    ))

        # Method parameter/return type relationships (dependency)
        seen_deps = set()
        for method in class_info.methods:
            # Check return type
            ret_type = self._extract_type_name(method.return_type)
            if ret_type and ret_type != class_name and ret_type not in seen_deps:
                if self._is_known_class(ret_type) and ret_type not in seen_members:
                    seen_deps.add(ret_type)

            # Check parameters
            for param_name, param_type in method.parameters:
                param_type_name = self._extract_type_name(param_type)
                if param_type_name and param_type_name != class_name:
                    if self._is_known_class(param_type_name):
                        if param_type_name not in seen_members and param_type_name not in seen_deps:
                            seen_deps.add(param_type_name)

        for dep in seen_deps:
            relationships.append(Relationship(
                from_class=class_name,
                to_class=dep,
                rel_type=RelationType.DEPENDENCY
            ))

        return relationships

    def _find_child_classes(self, parent_class: str) -> List[str]:
        """
        주어진 부모 클래스를 상속받는 모든 자식 클래스를 찾는다.

        역방향 상속 관계 탐색을 위해 사용된다.

        Args:
            parent_class: 부모 클래스 이름

        Returns:
            List[str]: 자식 클래스 이름 목록
        """
        children = []
        for class_name, class_info in self.parser.classes.items():
            if parent_class in class_info.base_classes:
                children.append(class_name)
        return children

    def _find_classes_using(self, target_class: str, allowed_types: Set = None) -> List[str]:
        """
        대상 클래스를 사용하는 모든 클래스를 찾는다.

        역방향 관계 탐색을 위해 사용된다. 멤버 변수나 메서드 매개변수로
        대상 클래스를 참조하는 클래스들을 찾는다.

        Args:
            target_class: 찾을 대상 클래스 이름
            allowed_types: 검색할 관계 유형 집합 (None이면 전체)

        Returns:
            List[str]: 대상 클래스를 사용하는 클래스 이름 목록
        """
        users = []
        for class_name, class_info in self.parser.classes.items():
            if class_name == target_class:
                continue

            found = False

            # Check members (composition/aggregation)
            if allowed_types is None or (allowed_types & {RelationType.COMPOSITION, RelationType.AGGREGATION}):
                for member in class_info.members:
                    type_name = self._extract_type_name(member.type_name)
                    if type_name == target_class:
                        users.append(class_name)
                        found = True
                        break

            # Check method parameters (dependency)
            if not found and (allowed_types is None or RelationType.DEPENDENCY in allowed_types):
                for method in class_info.methods:
                    for _, param_type in method.parameters:
                        type_name = self._extract_type_name(param_type)
                        if type_name == target_class:
                            users.append(class_name)
                            found = True
                            break
                    if found:
                        break

        return users

    def analyze_from_class(self, start_class: str, max_depth: int = 3,
                           rel_type_filter: List[str] = None) -> tuple:
        """
        시작 클래스에서 BFS로 관계를 분석한다.

        지정된 깊이까지 관련 클래스들을 탐색하며 관계를 수집한다.
        양방향 탐색을 수행하여 부모/자식 클래스와 사용자 클래스를 모두 찾는다.

        탐색 알고리즘:
            1. 시작 클래스를 큐에 추가
            2. 큐에서 클래스를 꺼내 관계 분석
            3. 관련 클래스들을 큐에 추가 (깊이 제한 내)
            4. 역방향 관계도 탐색 (자식 클래스, 사용자 클래스)
            5. 모든 클래스 방문 완료 또는 깊이 초과 시 종료

        Args:
            start_class: 시작 클래스 이름
            max_depth: 최대 탐색 깊이 (기본값: 3)
            rel_type_filter: 포함할 관계 유형 목록 (None이면 전체)
                            옵션: 'inheritance', 'composition',
                            'aggregation', 'dependency'

        Returns:
            tuple: (방문한 클래스명 집합, 관계 목록)
        """
        if start_class not in self.parser.classes:
            return set(), []

        # Convert filter to RelationType enum values
        allowed_types = None
        if rel_type_filter:
            type_map = {
                'inheritance': RelationType.INHERITANCE,
                'composition': RelationType.COMPOSITION,
                'aggregation': RelationType.AGGREGATION,
                'dependency': RelationType.DEPENDENCY
            }
            allowed_types = {type_map[t] for t in rel_type_filter if t in type_map}

        visited: Set[str] = set()
        relationships: List[Relationship] = []
        queue = deque([(start_class, 0)])

        while queue:
            class_name, depth = queue.popleft()

            if class_name in visited:
                continue

            visited.add(class_name)

            if class_name not in self.parser.classes:
                continue

            class_info = self.parser.classes[class_name]
            class_rels = self._analyze_class(class_info)

            for rel in class_rels:
                # Filter by relationship type
                if allowed_types and rel.rel_type not in allowed_types:
                    continue

                relationships.append(rel)

                # Add related classes to queue if within depth
                if depth < max_depth:
                    if rel.to_class not in visited:
                        queue.append((rel.to_class, depth + 1))
                    if rel.from_class not in visited:
                        queue.append((rel.from_class, depth + 1))

            # Also find child classes (classes that inherit from this class)
            # Only if inheritance is allowed
            if depth < max_depth:
                if allowed_types is None or RelationType.INHERITANCE in allowed_types:
                    for child in self._find_child_classes(class_name):
                        if child not in visited:
                            queue.append((child, depth + 1))

                # Also find classes that use this class (composition/aggregation/dependency)
                if allowed_types is None or (allowed_types & {RelationType.COMPOSITION,
                                                              RelationType.AGGREGATION,
                                                              RelationType.DEPENDENCY}):
                    for user in self._find_classes_using(class_name, allowed_types):
                        if user not in visited:
                            queue.append((user, depth + 1))

        # Remove duplicate relationships
        seen = set()
        unique_rels = []
        for rel in relationships:
            key = (rel.from_class, rel.to_class, rel.rel_type)
            if key not in seen:
                seen.add(key)
                unique_rels.append(rel)

        return visited, unique_rels

    def analyze_all(self) -> tuple:
        """
        모든 클래스 간의 관계를 분석한다.

        깊이 제한 없이 파싱된 모든 클래스의 관계를 추출한다.
        중복 관계는 자동으로 제거된다.

        Returns:
            tuple: (전체 클래스명 집합, 전체 관계 목록)
        """
        all_classes = set(self.parser.classes.keys())
        all_relationships = []

        for class_name in self.parser.classes:
            class_info = self.parser.classes[class_name]
            rels = self._analyze_class(class_info)
            all_relationships.extend(rels)

        # Remove duplicates
        seen = set()
        unique_rels = []
        for rel in all_relationships:
            key = (rel.from_class, rel.to_class, rel.rel_type)
            if key not in seen:
                seen.add(key)
                unique_rels.append(rel)

        return all_classes, unique_rels
