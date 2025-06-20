from sample_exec import sample_exec_paths, sample_height, sample_width
from matplotlib import cm

def compute_heatmap(paths, width, height, num_agents = 20):
    heatmap = [[0 for i in range(width)] for j in range(height)]
    for path in paths.values():
        for i in range(len(path)-1):
            if path[i] == path[i+1]:
                heatmap[path[i][0]][path[i][1]] += 1
    print_heatmap(heatmap)

def print_heatmap(heatmap):
    for i in range(len(heatmap)):
        print(heatmap[i])
compute_heatmap(sample_exec_paths,sample_width, sample_height)






