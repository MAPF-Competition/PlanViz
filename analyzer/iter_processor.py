# -*- coding: UTF-8 -*-

import matplotlib.pyplot as plt

DIR_NAME = "/home/rdaneel/my_exp/warehouse-10-20-10-2-1/CBSH2-CHBP/"
INS_NUM = 25

run_instances = []
for ins in range(1,INS_NUM+1,1):
    FILE_NAME = DIR_NAME + "warehouse-10-20-10-2-1-random-"\
        + str(ins) + "-130-0-CBSH2-CHBP-iter.txt"
    cur_ins = {"id":ins}
    with open(FILE_NAME, mode="r", encoding="utf-8") as fin:
        cur_ins["min_f_val"] = int(fin.readline().strip("\n").split(",")[-1])
        cur_ins["root_g_val"] = int(fin.readline().strip("\n").split(",")[-1])
        cur_ins["root_h_val"] = int(fin.readline().strip("\n").split(",")[-1])
        cur_ins["root_f_val"] = int(fin.readline().strip("\n").split(",")[-1])

        fin.readline()  # Skip the iter_nid

        cur_ins["iter_gval"] = []
        cur_ins["incr_gval"] = []
        line = fin.readline().strip("\n").split(",")
        line.pop(0)
        line.pop(-1)
        for _val_ in line:
            cur_ins["iter_gval"].append(int(_val_))
            cur_ins["incr_gval"].append(int(_val_) - cur_ins["root_g_val"])

        cur_ins["iter_hval"] = []
        cur_ins["incr_hval"] = []
        line = fin.readline().strip("\n").split(",")
        line.pop(0)
        line.pop(-1)
        for _val_ in line:
            cur_ins["iter_hval"].append(int(_val_))
            cur_ins["incr_hval"].append(int(_val_) - cur_ins["root_h_val"])

        cur_ins["iter_fval"] = []
        cur_ins["incr_fval"] = []
        line = fin.readline().strip("\n").split(",")
        line.pop(0)
        line.pop(-1)
        for _val_ in line:
            cur_ins["iter_fval"].append(int(_val_))
            cur_ins["incr_fval"].append(int(_val_) - cur_ins["root_f_val"])

        run_instances.append(cur_ins)


with open(DIR_NAME+"warehouse-10-20-10-2-1-random-130-CBSH2-CHBP.csv",
          mode="r", encoding="utf-8") as fin:
    fin.readline()
    for ins in range(INS_NUM):
        line = fin.readline()
        runtime = float(line.strip("\n").split(",")[0])
        run_instances[ins]["runtime"] = runtime
        if runtime > 60:
            run_instances[ins]["succ"] = False
        else:
            run_instances[ins]["succ"] = True

# for ins in range(INS_NUM):
#     plt.plot(run_instances[ins]["iter_hval"],
#              label="ins"+str(ins+1),
#              linewidth=1.5)

#     INS_MARKER = "x" if run_instances[ins]["succ"] is False else "o"
#     plt.scatter(len(run_instances[ins]["iter_hval"])-1,
#                 run_instances[ins]["iter_hval"][-1],
#                 marker=INS_MARKER)

#     plt.xticks(fontsize=14)
#     plt.xlabel("Interation", fontsize=14)

#     plt.yticks(fontsize=14)
#     plt.ylabel("h increment", fontsize=14)

PLOT_LABEL = "incr_gval"
for ins in range(INS_NUM):
    # if run_instances[ins]["succ"] is True:
    plt.plot(run_instances[ins][PLOT_LABEL],
            label="ins"+str(ins+1),
            linewidth=1.5)

    INS_MARKER = "x" if run_instances[ins]["succ"] is False else "o"
    plt.scatter(len(run_instances[ins][PLOT_LABEL])-1,
                run_instances[ins][PLOT_LABEL][-1],
                marker=INS_MARKER)

    plt.xticks(fontsize=14)
    plt.xlabel("Interation", fontsize=14)

    plt.yticks(fontsize=14)
    plt.ylabel("g increment", fontsize=14)

plt.legend()
plt.show()
