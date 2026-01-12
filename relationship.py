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
    INHERITANCE = "inheritance"     # A <|-- B (B inherits A)
    COMPOSITION = "composition"     # A *-- B (A contains B as value)
    AGGREGATION = "aggregation"     # A o-- B (A contains B as pointer/ref)
    DEPENDENCY = "dependency"       # A ..> B (A uses B in method)


@dataclass
class Relationship:
    from_class: str
    to_class: str
    rel_type: RelationType
    label: str = ""


class RelationshipAnalyzer:
    def __init__(self, parser: CppParser):
        """
        Initialize the relationship analyzer.

        Args:
            parser: CppParser instance with parsed classes
        """
        self.parser = parser
        self.relationships: List[Relationship] = []

    def _extract_type_name(self, type_str: str) -> Optional[str]:
        """
        Extract the core class name from a type string.
        Handles templates, pointers, references, etc.
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
        """Check if type is a pointer or reference."""
        type_str = type_str.strip()
        return type_str.endswith('*') or type_str.endswith('&')

    def _is_known_class(self, type_name: str) -> bool:
        """Check if the type name is a known class."""
        return type_name in self.parser.classes

    def _analyze_class(self, class_info: ClassInfo) -> List[Relationship]:
        """Analyze relationships for a single class."""
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
        """Find all classes that inherit from the given parent class."""
        children = []
        for class_name, class_info in self.parser.classes.items():
            if parent_class in class_info.base_classes:
                children.append(class_name)
        return children

    def _find_classes_using(self, target_class: str, allowed_types: Set = None) -> List[str]:
        """Find all classes that use the given class (as member or parameter).

        Args:
            target_class: The class to find users of
            allowed_types: Set of RelationType to filter by (None = all)
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
        Analyze relationships starting from a specific class using BFS.

        Args:
            start_class: The starting class name
            max_depth: Maximum depth to traverse (default: 3)
            rel_type_filter: List of relationship types to include
                           (None = all types). Options: 'inheritance',
                           'composition', 'aggregation', 'dependency'

        Returns:
            Tuple of (set of class names, list of relationships)
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
        Analyze all relationships between all classes.

        Returns:
            Tuple of (set of class names, list of relationships)
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
