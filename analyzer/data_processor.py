# -*- coding: UTF-8 -*-
"""Data processor"""

import logging
import os
import sys
import argparse
from typing import Dict, List
import yaml
import matplotlib.pyplot as plt
from util import get_csv_instance
import numpy as np

MAX_X_NUM:int = 5
MAX_Y_NUM:int = 6
NUM_SOLVERS_PER_ROW:int = 7

UNIT_GAPS:List = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500]
LARGE_MAPS:List[str] = ['den520d',
                        'warehouse-10-20-10-2-1',
                        'warehouse-20-40-10-2-1',
                        'warehouse-20-40-10-2-2']

OPERATIONS:Dict[str,str] = {'add': '+', 'sub': '-', 'mul': '*', 'div': '/', 'mod': '%'}
UNITS:Dict[int,str] = {1:'', 1000: ' (K)', 1000000: ' (M)'}
FIG_AXS:Dict = {1:(1,1), 2:(1,2), 3:(1,3), 4:(2,2), 6:(2,3), 8:(2,4), 9:(3,3)}
X_LABELS:Dict = {'num': 'Number of agents', 'ins': 'Instance', 'total': 'Total'}
Y_LABELS:Dict = {'succ': 'Success rate',
                 'runtime': 'Runtime (s)',
                 'runtime of detecting conflicts': 'Runtime (s)',
                 'runtime of path finding': 'Runtime (s)',
                 'solution cost': 'SOC',
                 '#low-level generated': 'Number of generated nodes',
                 '#low-level expanded': 'Number of expansions',
                 '#high-level generated': 'Number of generated nodes',
                 '#high-level expanded': 'Number expansions',
                 '#pathfinding': 'Number of replaned agents',
                 '#low-level search calls': 'Number of calls',
                 '#backtrack': 'Number of backtrackings',
                 '#restarts': 'Number of restarts',
                 'num_total_conf': 'Number of total conflicts'}


class DataProcessor:
    """Date processor for MAPF analysis
    """
    def __init__(self, config_file:str=None) -> None:
        self.config:Dict = {}
        config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), config_file)
        with open(config_path, mode="r", encoding="UTF-8") as fin:
            self.config = yaml.load(fin, Loader=yaml.FullLoader)

        self.num_ins_per_file = -1
        self.result = {}

    def get_row_val(self, in_index:str='succ'):
        """Compute the success rate versus the numbers of agents

        Args:
            in_index (str, optional): which data we want to analyze. Defaults to 'runtime'.

        Returns:
            Dict: the value of each solver per instance
        """

        result: Dict = {}
        for _sol_ in self.config['solvers']:
            result[_sol_['name']] = {}

            for _map_ in self.config['maps']:
                result[_sol_['name']][_map_['name']] = {}

                for _num_ in _map_['num_of_agents']:
                    result[_sol_['name']][_map_['name']][_num_] = {'ins':[], 'val':[], 'succ':[]}

                    for scen in _map_['scens']:
                        data_frame = get_csv_instance(self.config['exp_path'],
                                                      _map_['name'],
                                                      scen,
                                                      _num_,
                                                      _sol_['name'])
                        self.num_ins_per_file = data_frame.shape[0]

                        for i, row in data_frame.iterrows():
                            # Check if this instance is solved successfully
                            is_succ = row['solution cost'] >= 0 and \
                                row['runtime'] <= self.config['time_limit']

                            # Get the value of an instance
                            curr_val = None
                            if in_index == 'succ':
                                curr_val = int(is_succ)

                            elif in_index == 'runtime':
                                curr_val = min(row[in_index], self.config['time_limit'])

                            elif in_index == 'solution cost':
                                curr_val = row[in_index] if is_succ else np.inf

                            else:
                                curr_val = row[in_index]

                            result[_sol_['name']][_map_['name']][_num_]['val'].append(curr_val)
                            result[_sol_['name']][_map_['name']][_num_]['succ'].append(is_succ)
                            result[_sol_['name']][_map_['name']][_num_]['ins'].append(i+1)
        return result


    def operate_val(self, in_data1:Dict, in_data2:Dict, in_op:str):
        """Perform operation on in_data1 and in_data2

        Args:
            in_data1 (Dict): row data from the csv files
            in_data2 (Dict): row data from the csv files
            in_op (str, optional): which operation to perform.
        """
        assert in_op in OPERATIONS

        result = in_data1
        for _map_ in self.config['maps']:
            for _num_ in _map_['num_of_agents']:
                for _sol_ in self.config['solvers']:
                    for idx in range(self.num_ins_per_file):
                        val1 = in_data1[_sol_['name']][_map_['name']][_num_]['val'][idx]
                        val2 = in_data2[_sol_['name']][_map_['name']][_num_]['val'][idx]

                        if in_op == 'add':
                            tmp_val = val1 + val2
                        elif in_op == 'sub':
                            tmp_val = val1 - val2
                        elif in_op == 'mul':
                            tmp_val = val1 * val2
                        elif in_op == 'div':
                            tmp_val = val1 / val2 if val2 != 0 else np.inf
                        elif in_op != 'mod':
                            tmp_val = val1 % val2
                        else:
                            logging.error("Invalid operator!")
                            sys.exit()
                        result[_sol_['name']][_map_['name']][_num_]['val'][idx] = tmp_val
        return result


    def filter_val(self, in_data:Dict, in_filter:str=None):
        """Filter out values

        Args:
            in_data (Dict): the row data
            in_filter (str, optional): How to filter ('succ', 'common'). Defaults to None.

        Returns:
            results (Dict): row dataafter filtering
        """
        results:Dict = in_data
        if in_filter == 'succ':  # Only want the successfully-solved instances
            for _map_ in self.config['maps']:
                for _num_ in _map_['num_of_agents']:
                    for _sol_ in self.config['solvers']:
                        for idx in range(self.num_ins_per_file):
                            if not results[_sol_['name']][_map_['name']][_num_]['succ'][idx]:
                                results[_sol_['name']][_map_['name']][_num_]['val'][idx] = np.inf

        elif in_filter == 'common':
            for _map_ in self.config['maps']:
                for _num_ in _map_['num_of_agents']:
                    for idx in range(self.num_ins_per_file):
                        all_succ = True
                        for _sol_ in self.config['solvers']:
                            if not results[_sol_['name']][_map_['name']][_num_]['succ'][idx]:
                                all_succ = False
                                break

                        if not all_succ:
                            for _sol_ in self.config['solvers']:
                                results[_sol_['name']][_map_['name']][_num_]['val'][idx] = np.inf

        else:
            assert in_filter is None

        return results


    def get_val(self, base_analysis:str='num', y_index1:str='succ', y_index2:str=None,
                ins_op:str=None, in_filter:str='none', num_op:str='avg'):
        """Get the value on the y axid
        Args:
            base_analysis (str, optional):   value of the x-axid. Defaults to 'num'.
            y_index (str, optional):   value of the y-axid. Defaults to 'succ'.
            ins_op (str, optional):    operation for instance. Defaults to None.
            in_filter (str, optional): what data to ignore (none, succ, common). Defaults to 'none'.
            num_op (str, optional):    operation for number of agents (avg, sum). Defaults to 'avg'.

        Returns:
            Dict: the y value on the y axid
        """

        result = {}
        for _sol_ in self.config['solvers']:
            result[_sol_['name']] = {}
            for _map_ in self.config['maps']:
                result[_sol_['name']][_map_['name']] = {'x':[], 'val':[], 'var':[]}

        row_data = self.get_row_val(y_index1)  # Get all the instances
        if y_index2 is not None:
            row_data2 = {}
            row_data2 = self.get_row_val(y_index2)  # Get all the instances
            row_data = self.operate_val(row_data, row_data2, ins_op)  # Operate the data
        row_data = self.filter_val(row_data, in_filter)  # Filter out the data

        for _sol_ in self.config['solvers']:
            for _map_ in self.config['maps']:
                total_sum = 0.0
                total_num = 0
                global_idx = 1
                for _num_ in _map_['num_of_agents']:
                    ins_val = []
                    ins_sum = 0.0
                    ins_var = 0.0
                    ins_num = 0
                    for _val_ in row_data[_sol_['name']][_map_['name']][_num_]['val']:
                        if base_analysis == 'ins':  # instance-wise plot
                            result[_sol_['name']][_map_['name']]['val'].append(_val_)
                            result[_sol_['name']][_map_['name']]['x'].append(global_idx)
                        ins_val.append(_val_)
                        ins_sum += _val_
                        ins_num += 1
                        global_idx += 1

                    total_sum += ins_sum  # total plot
                    total_num += ins_num

                    if num_op == 'avg':  # Get the average of values among all instances
                        ins_sum = ins_sum / ins_num if ins_num > 0 else 0
                        if self.config['variation'] == 'std':  # standard deviation
                            ins_var = np.std(ins_val)
                        elif self.config['variation'] == 'ci':  # confidence interval
                            ins_var = 1.96*np.std(ins_val) / np.sqrt(ins_num)
                    else:
                        assert num_op == 'sum'

                    if base_analysis == 'num':  # number-of-agents-wise plot
                        result[_sol_['name']][_map_['name']]['val'].append(ins_sum)
                        result[_sol_['name']][_map_['name']]['var'].append(ins_var)
                        result[_sol_['name']][_map_['name']]['x'].append(_num_)

                if base_analysis == 'total':
                    if num_op == 'avg':
                        total_sum = total_sum / total_num if total_num > 0 else 0
                    else:
                        assert num_op == 'sum'
                    result[_sol_['name']][_map_['name']]['val'].append(total_sum)
                    result[_sol_['name']][_map_['name']]['x'].append(total_num)
        return result


    def change_ins_color(self, in_map):
        r_data = self.get_row_val()  # Get all the instances
        for _sol_ in self.config['solvers']:
            _sol_['color'] = []
            for _nid_, _num_ in enumerate(in_map['num_of_agents']):
                for _ in r_data[_sol_['name']][in_map['name']][_num_]['ins']:
                    _cid_ = min(_nid_, len(in_map['color'])-1)
                    _sol_['color'].append(in_map['color'][_cid_])


    def change_ins_markers(self):
        r_data = self.get_row_val()  # Get all the instances
        for _sol_ in self.config['solvers']:
            _sol_['marker'] = []
            for _map_ in self.config['maps']:
                for _num_ in _map_['num_of_agents']:
                    for _succ_ in r_data[_sol_['name']][_map_['name']][_num_]['succ']:
                        if self.config['succ_fail']:
                            new_marker = 'o' if _succ_ else 'X'
                            _sol_['marker'].append(new_marker)


    def get_subfig_position(self, f_idx:int):
        """Transfer subplot index to 2-D position
        Args:
            f_idx (int): subplot index

        Returns:
            int, int: 2D position
        """
        f_row = FIG_AXS[len(self.config['maps'])][1]
        return f_idx // f_row, f_idx % f_row


    def subplot_fig(self, in_axs, in_map_idx:int, in_map:Dict,
                    base_analysis:str, x_index:str, y_index:str,
                    x_label:str=None, y_label:str=None,
                    num_op:str='avg', in_filter:str=None, sort_by:str=None):
        """Plot the sub-figure
        """

        left_bd = -1 * self.config['set_shift']
        right_bd = self.config['set_shift']
        plt_rng = (right_bd - left_bd) / len(self.config['solvers'])

        for s_idx, _sol_ in enumerate(self.config['solvers']):
            # Get the values on the x axes
            _x_ = self.result[_sol_['name']][in_map['name']]['x']
            _num_ = range(1, len(_x_)+1)  # use for shifting the points
            if abs(self.config['set_shift']) > 0:
                _num_ = [_n_ + plt_rng*s_idx for _n_ in _num_]

            # Get the values and variations on the y axes
            _val_ = self.result[_sol_['name']][in_map['name']]['val']
            _var_ = self.result[_sol_['name']][in_map['name']]['var']

            # Plot the results of a solver on the map
            mf_color = _sol_['markerfacecolor'] if 'markerfacecolor' in _sol_.keys() else 'white'
            plot_label = _sol_['label'] if in_map_idx == 0 else None
            if self.config['variation'] in ('std', 'ci'):
                assert len(_var_) > 0
                assert x_index == 'num'
                in_axs.errorbar(_num_, _val_, yerr=_var_,
                                label=plot_label,
                                color=_sol_['color'],
                                marker=_sol_['marker'],
                                zorder=_sol_['zorder'],
                                linewidth=self.config['line_width'],
                                markerfacecolor=mf_color,
                                markeredgewidth=self.config['marker_width'],
                                ms=self.config['marker_size'],
                                alpha=self.config['alpha'])
                # Plot variation of the data
                assert len(_var_) > 0
                _lb_ = [_val_[i] - _var_[i] for i in range(len(_val_))]
                _ub_ = [_val_[i] + _var_[i] for i in range(len(_val_))]
                in_axs.fill_between(_num_, _lb_, _ub_, color=_sol_['color'], alpha=0.2)

            elif x_index in ('num', 'total'):
                in_axs.plot(_num_, _val_,
                            label=plot_label,
                            color=_sol_['color'],
                            marker=_sol_['marker'],
                            zorder=_sol_['zorder'],
                            linewidth=self.config['line_width'],
                            markerfacecolor=mf_color,
                            markeredgewidth=self.config['marker_width'],
                            ms=self.config['marker_size'],
                            alpha=self.config['alpha'])

            else:
                if 'color' in in_map:
                    self.change_ins_color(in_map)
                if self.config['succ_fail']:
                    self.change_ins_markers()
                if self.config['sort']:
                    self.sort_data()

                # Extend one color and marker to a list, one for each point
                if isinstance(_sol_['color'], str):
                    _sol_['color'] = [_sol_['color'] for _ in range(len(_val_))]
                if isinstance(_sol_['marker'], str):
                    _sol_['marker'] = [_sol_['marker'] for _ in range(len(_val_))]

                label_list = []
                label_list.append(plot_label)
                for _ in range(len(_val_)-1):
                    label_list.append(None)

                # _x_ = _num_ if x_index == 'ins' else _x_  # Check what value to plot
                _num_ = _x_ if x_index != 'ins' else _num_  # Check what value to plot
                for i, _v_ in enumerate(_val_):
                    in_axs.scatter(_num_[i], _v_,
                                   label=label_list[i],
                                   edgecolor=_sol_['color'][i],
                                   marker=_sol_['marker'][i],
                                   zorder=_sol_['zorder'],
                                   facecolor=mf_color,
                                   linewidth=self.config['marker_width']-1,
                                   s=self.config['marker_size']**1.8,
                                   alpha=self.config['alpha'])

        if self.config['set_title']:
            in_axs.set_title(in_map['label'], fontsize=self.config['text_size'])
        if self.config['y_grid']:
            in_axs.yaxis.grid()
        if self.config['x_grid']:
            in_axs.xaxis.grid()

        # Set the x-axis labels and positions
        x_unit = 1
        if x_index == 'num':
            in_axs.axes.set_xticks(_num_)
            in_axs.axes.set_xticklabels(_x_, fontsize=self.config['text_size'])
        elif len(_num_) > MAX_X_NUM and x_index == 'ins':
            _num_ = list(range(len(_x_)//MAX_X_NUM, len(_x_)+1, len(_x_)//MAX_X_NUM))
            _num_.insert(0, 1)
            _x_ = [_x_[_nn_-1] for _nn_ in _num_]
            in_axs.axes.set_xticks(_num_)
            in_axs.axes.set_xticklabels(_x_, fontsize=self.config['text_size'])
        else:
            x_ticks = in_axs.axes.get_xticks()
            shown_ticks = x_ticks
            if x_index == 'succ':
                x_ticks = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
                shown_ticks = x_ticks
            elif x_index == 'runtime' and num_op != 'sum':
                x_ticks = range(0, self.config['time_limit']+1, self.config['time_gap'])
                shown_ticks = x_ticks
            else:
                max_x_ticks = max(x_ticks)
                x_base = np.floor(np.log10(abs(max_x_ticks)))
                x_unit = 1
                if 2 < x_base <= 4:
                    x_unit = 1000
                elif 4 < x_base:
                    x_unit = 1000000

                x_gap = 1
                x_num = 1
                for _gap_ in UNIT_GAPS:
                    x_gap = _gap_ *  x_unit
                    x_num = int(np.ceil(max_x_ticks / x_gap))
                    if 1 < x_num < MAX_Y_NUM:
                        break

                x_ticks = []
                for _x_ in range(x_num+1):
                    x_ticks.append(_x_ * x_gap)

                if isinstance(x_gap, float):
                    shown_ticks = [f"{_x_/x_unit:.1f}" if _x_ > 0 else "0" for _x_ in x_ticks]
                elif isinstance(x_gap, int):
                    shown_ticks = [str(int(_x_//x_unit)) for _x_ in x_ticks]

            in_axs.axes.set_xticks(x_ticks)
            in_axs.axes.set_xticklabels(shown_ticks, fontsize=self.config['text_size'])

        if x_label is not None:
            shown_x_label = x_label
        elif x_index in X_LABELS:
            shown_x_label = X_LABELS[x_index]
            shown_x_label += UNITS[x_unit]
        elif x_index in Y_LABELS:
            shown_x_label = Y_LABELS[x_index]
            shown_x_label += UNITS[x_unit]
        else:
            logging.error("Missing x label text")
            sys.exit()
        in_axs.set_xlabel(shown_x_label, fontsize=self.config['text_size'])

        # Set the y-axis labels and positions
        y_ticks = in_axs.axes.get_yticks()
        shown_ticks = y_ticks
        y_unit = 1
        if y_index == 'succ':
            y_ticks = [0, 0.2, 0.4, 0.6, 0.8, 1.0]
            shown_ticks = y_ticks
        elif y_index == 'runtime' and num_op != 'sum':
            y_ticks = range(0, self.config['time_limit']+1, self.config['time_gap'])
            shown_ticks = y_ticks
        else:
            max_y_ticks = max(y_ticks)
            y_gap = -1
            y_num = -1
            for y_unit in UNITS:
                for _gap_ in UNIT_GAPS:
                    y_gap = _gap_ *  y_unit
                    y_num = int(np.ceil(max_y_ticks / y_gap))
                    if 1 < y_num < MAX_Y_NUM:
                        break
                if 1 < y_num < MAX_Y_NUM:
                    break
            assert y_gap > 0 and y_num > 0

            y_ticks = []
            for _y_ in range(y_num+1):
                y_ticks.append(_y_ * y_gap)

            if isinstance(y_gap, float):
                shown_ticks = [f"{_y_/y_unit:.1f}" if _y_ > 0 else "0" for _y_ in y_ticks]
            elif isinstance(y_gap, int):
                shown_ticks = [str(int(_y_//y_unit)) for _y_ in y_ticks]

        in_axs.axes.set_yticks(y_ticks)
        in_axs.axes.set_yticklabels(shown_ticks, fontsize=self.config['text_size'])

        if y_label is not None:
            shown_y_label = y_label
        elif y_index in Y_LABELS:
            shown_y_label = Y_LABELS[y_index]
        else:
            logging.error("Missing y label text")
            sys.exit()
        shown_y_label += UNITS[y_unit]
        in_axs.set_ylabel(shown_y_label, fontsize=self.config['text_size'])


    def sort_data(self):
        for _sol_ in self.config['solvers']:
            for _map_ in self.config['maps']:
                tmp_x = self.result[_sol_['name']][_map_['name']]['x']
                tmp_val = self.result[_sol_['name']][_map_['name']]['val']
                rst = [x for _,x in sorted(zip(tmp_x, tmp_val))]
                self.result[_sol_['name']][_map_['name']]['val'] = rst
                self.result[_sol_['name']][_map_['name']]['x'] = sorted(tmp_x)

                if isinstance(_sol_['color'], list):  # multiple colors in a solver (bug!)
                    _sol_['color'] = [x for _,x in sorted(zip(tmp_x, _sol_['color']))]
                if isinstance(_sol_['marker'], list):  # multiple markers in a solver
                    _sol_['marker'] = [x for _,x in sorted(zip(tmp_x, _sol_['marker']))]


    # def sort_data(self, sort_by:List[str]=None, in_filter:str=None, num_op:str='avg'):
    #     """Sort the data in self.result according to properties in sort_y
    #     """
    #     _y2_ = sort_by['y_index2'] if 'y_index2' in sort_by else None
    #     _op_ = sort_by['ins_op'] if 'ins_op' in sort_by else None
    #     comp_data = self.get_val('ins', sort_by['y_index1'], _y2_, _op_, in_filter, num_op)

    #     for _sol_ in self.config['solvers']:
    #         for _map_ in self.config['maps']:
    #             rst = [x for _,x in sorted(zip(comp_data[_sol_['name']][_map_['name']]['val'],
    #                                            self.result[_sol_['name']][_map_['name']]['val']))]
    #             self.result[_sol_['name']][_map_['name']]['val'] = rst
    #             self.result[_sol_['name']][_map_['name']]['x'] = sorted(comp_data[_sol_['name']][_map_['name']]['val'])

    #             if isinstance(_sol_['color'], list):  # multiple colors in a solver
    #                 _sol_['color'] = [x for _,x in sorted(zip(
    #                     comp_data[_sol_['name']][_map_['name']]['val'],
    #                     _sol_['color']))]
    #             if isinstance(_sol_['marker'], list):  # multiple markers in a solver
    #                 _sol_['marker'] = [x for _,x in sorted(zip(
    #                     comp_data[_sol_['name']][_map_['name']]['val'],
    #                     _sol_['marker']))]


    def plot_fig(self, base:str, x_index1:str, y_index1:str,
                 y_index2:str=None, y_op:str=None, y_label:str=None,
                 x_index2:str=None, x_op:str=None, x_label:str=None,
                 num_op:str='avg', in_filter:str=None, sort_by:str=None):
        """Plot the figure

        Args:
            base (str): how to analyze each point on the figure ('num' or 'ins').
            x_index (str): index on the x-axes ('num' or 'ins' or other properties).
            y_index1 (str): index on the y-axes.
            y_index2 (str, optional): index on the y-axes for operation. Defaults to None.
            y_label (str, optional): operation for y_index1 and y_index2. Defaults to None.
            num_op (str, optional): operation per number of agents. Defaults to 'avg'.
            ins_op (str, optional): operation per instance. Defaults to None.
            in_filter (str, optional): filter for the row data. Defaults to None.
        """
        # Get the results for the y axes
        self.result = self.get_val(base, y_index1, y_index2, y_op, in_filter, num_op)

        # Get the results for the x axes
        if x_index1 is None:
            x_index1 = base
        else:
            x_result = self.get_val(base, x_index1, x_index2, x_op, in_filter, num_op)
            for _sol_ in self.config['solvers']:
                for _map_ in self.config['maps']:
                    assert len(self.result[_sol_['name']][_map_['name']]['x']) ==\
                        len(x_result[_sol_['name']][_map_['name']]['val'])
                    self.result[_sol_['name']][_map_['name']]['x'] =\
                        x_result[_sol_['name']][_map_['name']]['val']

        # Plot all the subplots on the figure
        plt.close('all')  # Initialize the plot
        fig, axs = plt.subplots(nrows=FIG_AXS[len(self.config['maps'])][0],
                                ncols=FIG_AXS[len(self.config['maps'])][1],
                                figsize=(self.config['figure_width'],
                                         self.config['figure_height']),
                                dpi=80, facecolor='w', edgecolor='k')

        for _idx_, _map_  in enumerate(self.config['maps']):
            frow, fcol = self.get_subfig_position(_idx_)
            if len(self.config['maps']) == 1:
                self.subplot_fig(axs, _idx_, _map_,
                                 base, x_index1, y_index1,
                                 x_label, y_label,
                                 num_op, in_filter, sort_by)
            elif FIG_AXS[len(self.config['maps'])][0] == 1:
                self.subplot_fig(axs[fcol], _idx_, _map_,
                                 base, x_index1, y_index1,
                                 x_label, y_label,
                                 num_op, in_filter, sort_by)
            else:
                self.subplot_fig(axs[frow,fcol], _idx_, _map_,
                                 base, x_index1, y_index1,
                                 x_label, y_label,
                                 num_op, in_filter, sort_by)

        legend_ncols = len(self.config['solvers'])
        if len(self.config['solvers']) > NUM_SOLVERS_PER_ROW:
            legend_ncols = np.ceil(len(self.config['solvers'])) // 2

        if self.config['set_legend']:
            if len(self.config['maps']) > 1:
                fig.legend(loc="upper center",
                    bbox_to_anchor= (0.5, 1.01),
                    borderpad=0.1,
                    handletextpad=0.1,
                    labelspacing=0.1,
                    columnspacing=1.0,
                    ncol=legend_ncols,
                    fontsize=self.config['text_size'])
            else:
                plt.legend(loc="best", fontsize=self.config['text_size'])
        plt.tight_layout()
        plt.show()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Input: config.yaml and operations.yaml')
    parser.add_argument('--config', type=str, required=True)
    parser.add_argument('--oper', type=str, required=True)
    main_args = parser.parse_args()

    data_proc = DataProcessor(main_args.config)

    operations = {'y_index2': None,
                  'y_label': None,
                  'num_operation': 'avg',
                  'y_operation': None,
                  'x_index1': None,
                  'x_index2': None,
                  'x_operation': None,
                  'x_label': None,
                  'filter': None,
                  'sort_by': None}
    with open(main_args.oper, mode='r', encoding='utf-8') as fin_op:
        operations.update(yaml.load(fin_op, Loader=yaml.FullLoader))
    assert 'base_analysis' in operations and 'y_index1' in operations

    data_proc.plot_fig(operations['base_analysis'], operations['x_index1'], operations['y_index1'],
                       operations['y_index2'], operations['y_operation'], operations['y_label'],
                       operations['x_index2'], operations['x_operation'], operations['x_label'],
                       operations['num_operation'], operations['filter'], operations['sort_by'])
