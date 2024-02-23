import os
import sys
import datetime
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

def make_log(
    directory: str, 
    logParams: dict
):
    '''
    Convert dictionary of parameters to a log file and save it in the directory
    '''
    now = datetime.datetime.now()
    logPath = os.path.join(directory, f"!log-{now.strftime('%Y%m%d%H%M')}.txt")
    logFile = open(logPath, "w")                                    
    logFile.write("\n" + now.strftime("%Y-%m-%d %H:%M") + "\n")     
    for key, value in logParams.items():                            
        logFile.write('%s: %s\n' % (key, value))                    
    logFile.close()     

def ensure_group_names(
    folder_path: str,
    group_names: list,
    log_params: dict
) -> list:
    # list of file names in specified directory
    file_names = [fname for fname in os.listdir(folder_path) if fname.endswith('.tif') and not fname.startswith('.')]

    # list of groups that matched to file names
    groups_found = np.unique([group for group in group_names for file in file_names if group in file]).tolist()

    # dictionary of file names and their corresponding group names
    uniqueDic = {file : [group for group in group_names if group in file] for file in file_names}

    for file_name, matching_groups in uniqueDic.items():
        # if a file doesn't have a group name, log it but still run the script
        if len(matching_groups) == 0:
            log_params["Group Matching Errors"].append(f'{file_name} was not matched to a group')

        # if a file has multiple groups names, raise error and exit the script
        elif len(matching_groups) > 1:
            print('****** ERROR ******',
                f'\n{file_name} matched to multiple groups: {matching_groups}',
                '\nPlease fix errors and try again.',
                '\n****** ERROR ******')
            sys.exit()

    # if a group was specified but not matched to a file name, raise error and exit the script
    if len(groups_found) != len(group_names):
        print("****** ERROR ******",
            "\nOne or more groups were not matched to file names",
            f"\nGroups specified: {group_names}",
            f"\nGroups found: {groups_found}",
            "\n****** ERROR ******")
        sys.exit()      
    
    return file_names

def plotComparisons(
    dataFrame: pd.DataFrame, 
    dependent: str, 
    independent = 'Group Name'
) -> plt.Figure:
        '''
        This func accepts a dataframe, the name of a dependent variable, and the name of an
        independent variable (by default, set to Group Name). It returns a figure object showing
        a box and scatter plot of the dependent variable grouped by the independent variable.
        '''
        ax = sns.boxplot(x=independent, y=dependent, data=dataFrame, palette = "Set2", showfliers = False)
        ax = sns.swarmplot(x=independent, y=dependent, data=dataFrame, color=".25")	
        ax.set_xticklabels(ax.get_xticklabels(),rotation=45)
        fig = ax.get_figure()
        return fig

def generate_group_comparison(
    main_save_path: str,
    processor: object,
    summary_df: pd.DataFrame,
    log_params: dict
):
    print('Generating group comparisons...')
    # make a group comparisons save path in the main save directory
    group_save_path = os.path.join(main_save_path, "!groupComparisons")
    if not os.path.exists(group_save_path):
        os.makedirs(group_save_path)
    
    # make a list of parameters to compare
    stats_to_compare = ['Mean']
    channels_to_compare = [f'Ch {i+1}' for i in range(processor.num_channels)]
    measurements_to_compare = ['Period', 'Shift', 'Peak Width', 'Peak Max', 'Peak Min', 'Peak Amp', 'Peak Rel Amp']
    params_to_compare = []
    for channel in channels_to_compare:
        for stat in stats_to_compare:
            for measurement in measurements_to_compare:
                params_to_compare.append(f'{channel} {stat} {measurement}')

    # will compare the shifts if multichannel movie
    if hasattr(processor, 'channel_combos'):
        shifts_to_compare = [f'Ch{combo[0]+1}-Ch{combo[1]+1} Mean Shift' for combo in processor.channel_combos]
        params_to_compare.extend(shifts_to_compare)

    # generate and save figures for each parameter
    for param in params_to_compare:
        try:
            fig = plotComparisons(summary_df, param)
            fig.savefig(f'{group_save_path}/{param}.png')  # type: ignore
            plt.close(fig)
        except ValueError:
            log_params['Plotting errors'].append(f'No data to compare for {param}')
