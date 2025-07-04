from typing import List, Tuple, Dict
OBSTACLES: List[str] = ['@', 'T']


def load_map(map_file: str) -> None:
    env_map = []
    with open(file=map_file, mode="r", encoding="UTF-8") as fin:
        fin.readline()  # ignore type
        height = int(fin.readline().strip().split(' ')[1])
        width = int(fin.readline().strip().split(' ')[1])
        fin.readline()  # ignore 'map' line
        for line in fin.readlines():
            out_line: List[bool] = []
            for word in list(line.strip()):
                if word in OBSTACLES:
                    out_line.append(0)
                else:
                    out_line.append(1)
            assert len(out_line) == width
            env_map.append(out_line)
    assert len(env_map) == height
    return env_map

def create_adjacency_matrix(compiled_map_file):
    pass

def planviz_bfs(map_file):
    compiled_map = load_map(map_file)




map_compiled = load_map(r"C:\Users\steph\PycharmProjects\PlanViz\example\warehouse_small.map")

for i in range(len(map_compiled)):
    print(map_compiled[i])