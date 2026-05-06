import os
import ast

def remove_docstrings_from_file(filepath):
    """
    Lee un archivo Python, utiliza `ast` para encontrar las líneas exactas
    que contienen docstrings (cadenas de documentación en módulos, clases o funciones)
    y luego reescribe el archivo eliminando esas líneas.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
            
        tree = ast.parse(source)
    except SyntaxError:
        # Si el código tiene un error de sintaxis previo, lo omitimos para no corromperlo
        return False
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return False

    lines_to_remove = set()
    
    # Recorrer el árbol AST para buscar nodos que tengan un docstring
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            # get_docstring retorna el texto si existe
            if ast.get_docstring(node):
                # El docstring es siempre la primera expresión en el cuerpo del nodo
                doc_node = node.body[0]
                if isinstance(doc_node, ast.Expr) and isinstance(doc_node.value, ast.Constant) and isinstance(doc_node.value.value, str):
                    start = doc_node.lineno
                    end = doc_node.end_lineno
                    for line_idx in range(start, end + 1):
                        lines_to_remove.add(line_idx)
                        
    if not lines_to_remove:
        return False # No hay docstrings que remover

    # Reconstruir el archivo sin las líneas del docstring
    original_lines = source.split('\n')
    cleaned_lines = []
    
    for i, line in enumerate(original_lines, start=1):
        if i not in lines_to_remove:
            cleaned_lines.append(line)
            
    # Remoción adicional: colapsar líneas vacías extras para evitar "huecos grandes"
    final_lines = []
    for line in cleaned_lines:
        if line.strip() == '':
            if final_lines and final_lines[-1].strip() != '':
                pass # remove empty lines completely to match previous formatting style
        else:
            final_lines.append(line)

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(final_lines))
        return True
    except Exception as e:
        print(f"Error writing to {filepath}: {e}")
        return False

def process_directory(root_dir, exclude_dirs):
    processed = 0
    for root, dirs, files in os.walk(root_dir):
        # Excluir directorios como src/algorithms y node_modules
        dirs[:] = [d for d in dirs if d not in exclude_dirs and not os.path.join(root, d).endswith('algorithms') and  not os.path.join(root, d).endswith('indicators')]
        
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                if remove_docstrings_from_file(file_path):
                    processed += 1
                    print(f"Removed docstrings from: {file_path}")
                    
    print(f"Total Python files cleaned (docstrings removed): {processed}")

if __name__ == "__main__":
    root_dir = r"d:\Betas\QuntumLLamaV2.0.2Beta\src"
    exclude = {'algorithms', 'indicators', '__pycache__'}
    process_directory(root_dir, exclude)
