"""
PlantUML Generator
Generates PlantUML class diagram code from parsed C++ classes
"""

from typing import List, Set, Dict
from cpp_parser import ClassInfo, CppParser
from relationship import Relationship, RelationType


class PlantUMLGenerator:
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
        Initialize the PlantUML generator.

        Args:
            parser: CppParser instance with parsed classes
        """
        self.parser = parser

    def _format_type(self, type_str: str) -> str:
        """Format type string for PlantUML."""
        # Escape special characters
        type_str = type_str.replace("<", "~").replace(">", "~")
        return type_str

    def _generate_class(self, class_info: ClassInfo,
                        show_members: bool = True, show_methods: bool = True) -> str:
        """Generate PlantUML code for a single class.

        Args:
            class_info: ClassInfo object
            show_members: Whether to show member variables
            show_methods: Whether to show methods
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
        """Generate PlantUML code for a relationship."""
        arrow = self.RELATIONSHIP_ARROWS.get(rel.rel_type, "-->")

        if rel.label:
            return f"{rel.from_class} {arrow} {rel.to_class} : {rel.label}"
        else:
            return f"{rel.from_class} {arrow} {rel.to_class}"

    def generate(self, class_names: Set[str], relationships: List[Relationship],
                 title: str = None, component_options: dict = None) -> str:
        """
        Generate complete PlantUML diagram.

        Args:
            class_names: Set of class names to include
            relationships: List of relationships between classes
            title: Optional diagram title
            component_options: Dict with 'members' and 'methods' boolean keys

        Returns:
            PlantUML code as string
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
        Generate PlantUML starting from a specific class.

        Args:
            start_class: Starting class name
            max_depth: Maximum relationship depth
            title: Optional diagram title
            rel_type_filter: List of relationship types to include (None = all)
            component_options: Dict with 'members' and 'methods' boolean keys

        Returns:
            PlantUML code as string
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
        Generate PlantUML for all classes.

        Args:
            title: Optional diagram title

        Returns:
            PlantUML code as string
        """
        from relationship import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer(self.parser)
        classes, relationships = analyzer.analyze_all()

        if not title:
            title = "Full Class Diagram"

        return self.generate(classes, relationships, title)
