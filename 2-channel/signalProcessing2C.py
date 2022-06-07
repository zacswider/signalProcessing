import os                                       
import sys 
import pathlib   
import timeit
import datetime
import numpy as np
import pandas as pd
from custom_gui import CustomGUI
from signal_processing_class import SignalProcessor

np.seterr(divide='ignore', invalid='ignore')

'''** GUI Window and sanity checks'''
# make GUI object and display the window
gui = CustomGUI()
gui.mainloop()

# identify and report errors in GUI input
errors = []
if gui.acf_peak_thresh > 1 :
    errors.append("The ACF peak prominence can not be greater than 1",
                  ", set 'ACF peak prominence threshold' to a value between 0 and 1.",
                  "More realistically, a value between 0 and 0.5")
if len(gui.folder_path) < 1 :
    errors.append("You didn't enter a directory to analyze")

if len(errors) >= 1 :
    print("Error Log:")
    for count, error in enumerate(errors):
        print(count,":", error)
    sys.exit("Please fix errors and try again.") 

# get GUI parameters
box_size = gui.box_size
folder_path = gui.folder_path
group_names = gui.group_names
acf_peak_thresh = gui.acf_peak_thresh
plot_ind_ACFs = gui.plot_ind_ACFs
plot_ind_CCFs = gui.plot_ind_CCFs
plot_ind_peaks = gui.plot_ind_peaks

#make dictionary of parameters for log file use
log_params = {  "Box Size(px)" : box_size,
                "Base Directory" : folder_path,
                "ACF Peak Prominence" : acf_peak_thresh,
                "Group Names" : group_names,
                "Plot Individual ACFs" : plot_ind_ACFs,
                "Plot Individual CCFs" : plot_ind_CCFs,
                "Plot Individual Peaks" : plot_ind_peaks,
                "Group Matching Errors" : [],
                "Files Processed" : [],
                "Files Not Processed" : []
             }

''' ** housekeeping functions ** '''
def make_log(directory, logParams):
    '''
    Convert dictionary of parameters to a log file and save it in the directory
    '''
    logPath = os.path.join(directory, "0_log.txt")                    # path to log file
    now = datetime.datetime.now()                                   # get current date and time
    logFile = open(logPath, "w")                                    # initiate text file
    logFile.write("\n" + now.strftime("%Y-%m-%d %H:%M") + "\n")     # write current date and time
    for key, value in logParams.items():                            # for each key:value pair in the parameter dictionary...
        logFile.write('%s: %s\n' % (key, value))                    # write pair to new line
    logFile.close()                                                 # close the file

''' ** error catching for group names ** '''
# list of file names in specified directory
file_names = filelist = [fname for fname in os.listdir(folder_path) if fname.endswith('.tif') and not fname.startswith('.')]

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

''' ** Main Workflow ** '''
# performance tracker
start = timeit.default_timer()
# empty list to fill with file stats
stats_list = []
# emtpy list to fill with column headers
col_headers = []
# create main save path
main_save_path = os.path.join(folder_path, "0_signalProcessing")
# create directory if it doesn't exist
if not os.path.exists(main_save_path):
    os.makedirs(main_save_path)

# empty list to fill with summary data for each file
summary_list = []
# column headers to use with summary data during conversion to dataframe
col_headers = []

for file_name in file_names: 
    print(f"Starting to work on {file_name}")
    processor = SignalProcessor(image_path = f'{folder_path}/{file_name}', box_size = box_size)

    # log error and skip image if frames < 2 or channels >2
    if processor.num_frames < 2:
        print(f"****** ERROR ******",
              f"\n{file_name} has less than 2 frames",
              "\n****** ERROR ******")
        log_params['Files Not Processed'].append(f'{file_name} has less than 2 frames')
        continue
    if processor.num_channels > 2:
        print(f"****** ERROR ******",
              f"\n{file_name} has more than 2 channels",
              "\n****** ERROR ******")
        log_params['Files Not Processed'].append(f'{file_name} has more than 2 channels')
        continue
    
    # if file is not skipped, log it and continue
    log_params['Files Processed'].append(f'{file_name}')

    # name without the extension
    name_wo_ext = file_name.rsplit(".",1)[0]

    # set save path for output for each image file
    boxSavePath = pathlib.Path(folder_path + "/0_signalProcessing/" + name_wo_ext)
    boxSavePath.mkdir(exist_ok=True, parents=True)
    
    # if user entered group name(s) into GUI, match the group for this file
    if group_names != ['']:                                      # if user entered group names to compare...
        group_name = [group for group in group_names if group in name_wo_ext][0]

    # calculate the number of boxes used for analysis
    num_boxes = processor.x_boxes * processor.y_boxes

    # calculate autocorrelation for each channel for each box
    acf_results = processor.calc_ACF(peak_thresh = acf_peak_thresh)

    # if possible, calculate the cross correlation between channels for each box
    if processor.num_channels == 2:
        ccf_results = processor.calc_CCF()

    # calculate the peak properties (width, max, min, amp, relAmp) for each channel for each box
    peak_properties = processor.calc_peaks()
    
    # create a subfolder within the main save path with the same name as the image file
    im_save_path = os.path.join(main_save_path, name_wo_ext)
    if not os.path.exists(im_save_path):
        os.makedirs(im_save_path)

    # summaryize the data for current image as dataframe, and save as .csv
    im_measurements_df, im_summary_dict = processor.summarize_results()
    im_measurements_df.to_csv(f'{im_save_path}/{name_wo_ext}_measurements.csv', index = False)

    # populate column headers list with keys from the measurements dictionary
    for key in im_summary_dict.keys(): 
        if key not in col_headers: 
            col_headers.append(key) 
    
    # append summary data to the summary list
    summary_list.append(im_summary_dict)

    # plot and save the population autocorrelation results for each channel
    acf_plots = processor.plot_mean_CF()
    ch1_acf_plot = acf_plots['Ch1 ACF']
    ch1_acf_plot.savefig(f'{im_save_path}/{name_wo_ext}_Ch1_ACF.png')
    if processor.num_channels == 2:
        ch2_acf_plot = acf_plots['Ch2 ACF']
        ch2_acf_plot.savefig(f'{im_save_path}/{name_wo_ext}_Ch2_ACF.png')
        ccf_plot = acf_plots['Mean CCF']
        ccf_plot.savefig(f'{im_save_path}/{name_wo_ext}_CCF.png')

    # plot and save the population peak properties for each channel
    peak_plots = processor.plot_peak_props()
    ch1_peak_plot = peak_plots['Ch1']
    ch1_peak_plot.savefig(f'{im_save_path}/{name_wo_ext}_Ch1_Peaks.png')
    if processor.num_channels == 2:
        ch2_peak_plot = peak_plots['Ch2']
        ch2_peak_plot.savefig(f'{im_save_path}/{name_wo_ext}_Ch2_Peaks.png')


# convert summary_list to dataframe using the column headers and save to main save path
summary_df = pd.DataFrame(summary_list, columns = col_headers)
summary_df.to_csv(f'{main_save_path}/summary.csv', index = False)

end = timeit.default_timer()
log_params["Time Elapsed"] = f"{end - start:.2f} seconds"
# log parameters and errors
make_log(main_save_path, log_params)
