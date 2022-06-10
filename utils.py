from ast_nodes import Node, Operator


def escape(s: str):
    return (
        s.replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\b", "\\b")
        .replace("\r", "\\r")
        .replace("\f", "\\f")
        .replace("'", "\\'")
        .replace('"', '\\"')
        .replace("<", "\\<")
        .replace(">", "\\>")
        .replace("\n", "\\l")
        .replace("||", "\\|\\|")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("{", "\\{")
        .replace("}", "\\}")
    )


def graph_prologue():
    return (
        'digraph G {  graph [fontname = "Courier New"];\n'
        + ' node [fontname = "Courier"];\n'
        + ' edge [fontname = "Courier"];'
    )


def graph_epilogue():
    return "}"


def print_ast(ast_nodes: list[Node]):
    graph = [graph_prologue()]
    seen = set()
    for line_num, ast_node in enumerate(ast_nodes):
        name = f"line_{line_num}"
        graph.append(f"subgraph cluster_{escape(name)} {{ \n label = {escape(name)}")
        edges = []
        stack = []
        nodes = []
        stack.append(ast_node)
        seen.add(ast_node)

        while stack:
            node = stack.pop()
            if isinstance(node, Operator):
                nodes.append(
                    f'   {id(node)} [shape=circle, label="{escape(node.source())}"];'
                )
            elif node.is_terminal():
                nodes.append(
                    f'   {id(node)} [shape=oval, label="{escape(node.source())}"];'
                )
            else:
                nodes.append(
                    f'   {id(node)} [shape=record, style=filled, fillcolor=gray, label="<from_node>{escape(node.source())}"];'
                )

            for child in node.children():
                edges.append(f"    {id(node)}:from_false -> {id(child)}:from_node;")
                if child not in seen:
                    stack.append(child)

        graph.extend(edges)
        graph.extend(nodes)
        graph.append(graph_epilogue())
    graph.append(graph_epilogue())
    with open("ast.dot", "w") as f:
        f.write("\n".join(graph))