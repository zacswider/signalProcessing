import os
import csv
import timeit
import datetime
import pandas as pd
from tqdm import tqdm
from typing import Any
from waveanalysis.waveanalysismods.processor import TotalSignalProcessor

from waveanalysis.image_properties_signal.convert_images import convert_kymos, convert_movies  
from waveanalysis.housekeeping.housekeeping_functions import make_log, generate_group_comparison, group_name_error_check, check_and_make_save_path, save_plots, save_values_to_csv
from waveanalysis.image_properties_signal.image_properties import get_standard_image_properties, get_kymo_image_properties
from waveanalysis.image_properties_signal.create_np_arrays import create_array_from_kymo, create_array_from_standard_rolling
from waveanalysis.image_properties_signal.create_np_arrays import create_array_from_standard_rolling, create_array_from_kymo  
from waveanalysis.signal_processing import calc_indv_ACFs_periods, calc_indv_CCFs_shifts_channelCombos, calc_indv_peak_props
from waveanalysis.plotting import plot_indv_peak_props_workflow, plot_indv_acfs_workflow, plot_indv_ccfs_workflow, save_indv_ccfs_workflow, plot_mean_ACFs_workflow, plot_mean_prop_peaks_workflow, plot_mean_CCFs_workflow, save_mean_CCF_values_workflow, plot_rolling_mean_periods, plot_rolling_mean_shifts, plot_rolling_mean_peak_props
from waveanalysis.summarize_organize_savize.add_stats_for_parameter import save_parameter_means_to_csv



def standard_kymo_workflow(
    folder_path: str,
    group_names: list[str],
    log_params: dict[str, Any],
    analysis_type: str,
    box_size: int,
    box_shift: int,
    subframe_size: int,
    subframe_roll: int,
    line_width: int,
    acf_peak_thresh: float,
    plot_summary_ACFs: bool,
    plot_summary_CCFs: bool,
    plot_summary_peaks: bool,
    plot_ind_ACFs: bool,
    plot_ind_CCFs: bool,
    plot_ind_peaks: bool,
) -> pd.DataFrame:             

    # list of file names in specified directory
    file_names = [fname for fname in os.listdir(folder_path) if fname.endswith('.tif') and not fname.startswith('.')]
              
    # check for group name errors          
    group_name_error_check(file_names=file_names,
                           group_names=group_names, 
                           log_params=log_params)

    # performance tracker
    start = timeit.default_timer()

    # create main save path
    now = datetime.datetime.now()
    main_save_path = os.path.join(folder_path, f"0_signalProcessing-{now.strftime('%Y%m%d%H%M')}")
    check_and_make_save_path(main_save_path)

    # empty list to fill with summary data for each file
    summary_list = []
    # column headers to use with summary data during conversion to dataframe
    col_headers = []

    # convert images to numpy arrays
    if analysis_type == 'kymograph':
        all_images = convert_kymos(folder_path=folder_path)
    else:
        all_images = convert_movies(folder_path=folder_path)

    print('Processing files...')

    with tqdm(total = len(file_names)) as pbar:
        pbar.set_description('Files processed:')
        for file_name in file_names: 
            print('******'*10)
            print(f'Processing {file_name}...')

            # Get image properties
            image_path = f'{folder_path}/{file_name}'
            if analysis_type == 'kymograph':
                num_channels, total_columns, num_frames = get_kymo_image_properties(image_path=image_path, image=all_images[file_name])
            else:
                num_channels, num_frames = get_standard_image_properties(image_path=image_path)

            # TODO: Set the parameters for the signal processor that were not set in the log parameters
                
            num_submovies = None # set to none for now, but will completely remove this parameter in the future
            num_x_bins = None # set to none for now because kymo needs to be none
            num_y_bins = None # set to none for now because kymo needs to be none

            # Create the array for which all future processing will be based on
            if analysis_type == 'kymograph':
                bin_values, num_bins = create_array_from_kymo(
                                            line_width = line_width,
                                            total_columns = total_columns,
                                            step = box_shift,
                                            num_channels = num_channels,
                                            num_frames = num_frames,
                                            image = all_images[file_name]
                                        )
            else:
                bin_values, num_bins, num_x_bins, num_y_bins = create_array_from_standard_rolling(
                                                                    kernel_size = box_size, 
                                                                    step = box_shift, 
                                                                    num_channels = num_channels, 
                                                                    num_frames = num_frames, 
                                                                    image = all_images[file_name]
                                                                )
                


            processor = TotalSignalProcessor(analysis_type = analysis_type, 
                                             image_path = f'{folder_path}/{file_name}',
                                             image = all_images[file_name], 
                                             kern = box_size, 
                                             step = box_shift, 
                                             roll_size = subframe_size, 
                                             roll_by = subframe_roll, 
                                             line_width = line_width)
            
            # log error and skip image if frames < 2 
            if num_frames < 2:
                print(f"****** ERROR ******",
                    f"\n{file_name} has less than 2 frames",
                    "\n****** ERROR ******")
                log_params['Files Not Processed'].append(f'{file_name} has less than 2 frames')
                continue

            # if file is not skipped, log it and continue
            log_params['Files Processed'].append(f'{file_name}')

            # name without the extension
            name_wo_ext = file_name.rsplit(".",1)[0]

            # if user entered group name(s) into GUI, match the group for this file. If no match, keep set to None
            group_name = None
            if group_names != ['']:
                try:
                    group_name = [group for group in group_names if group in name_wo_ext][0]
                except IndexError:
                    pass

            # calculate the individual ACFs for each channel
            indv_acfs, indv_periods = calc_indv_ACFs_periods(
                num_channels=num_channels, 
                num_bins=num_bins, 
                num_frames=num_frames, 
                bin_values=bin_values, 
                analysis_type=analysis_type, 
                roll_size=subframe_size, 
                roll_by=subframe_roll, 
                num_submovies=num_submovies, 
                num_x_bins=num_x_bins, 
                num_y_bins=num_y_bins, 
                peak_thresh=acf_peak_thresh
                )
                
            # calculate the individual peak properties for each channel
            ind_peak_widths, ind_peak_maxs, ind_peak_mins, ind_peak_amps, ind_peak_rel_amps, ind_peak_props = calc_indv_peak_props(
                num_channels=num_channels,
                num_bins=num_bins,
                bin_values=bin_values,
                analysis_type=analysis_type,
                num_submovies=num_submovies,
                roll_by=subframe_roll,
                roll_size=subframe_size,
                num_x_bins=num_x_bins,
                num_y_bins=num_y_bins
            )

            # calculate the individual CCFs for each channel
            if num_channels > 1:
                indv_shifts, indv_ccfs, channel_combos = calc_indv_CCFs_shifts_channelCombos(
                    num_channels=num_channels,
                    num_bins=num_bins,
                    num_frames=num_frames,
                    bin_values=bin_values,
                    analysis_type=analysis_type,
                    roll_size=subframe_size,
                    roll_by=subframe_roll,
                    num_submovies=num_submovies,
                    periods=indv_periods
                )

            # The code snippet above creates a subfolder within the main save path with the same name as the image file. Will store all associated files in this subfolder
            im_save_path = os.path.join(main_save_path, name_wo_ext)
            check_and_make_save_path(im_save_path)

            # plot the mean ACF figures for the file
            if plot_summary_ACFs:
                mean_acf_plots = plot_mean_ACFs_workflow(
                    acfs=indv_acfs,
                    periods=indv_periods,
                    num_frames=num_frames,
                    num_channels=num_channels
                )
                save_plots(mean_acf_plots, im_save_path)

            # plot the mean peak properties figures for the file
            if plot_summary_peaks:
                mean_peak_plots = plot_mean_prop_peaks_workflow(
                    indv_peak_mins=ind_peak_mins,
                    indv_peak_maxs=ind_peak_maxs,
                    indv_peak_amps=ind_peak_amps,
                    indv_peak_widths=ind_peak_widths,
                    num_channels=num_channels
                )
                save_plots(mean_peak_plots, im_save_path)

            # plot the mean CCF figures for the file
            if plot_summary_CCFs:
                mean_ccf_plots = plot_mean_CCFs_workflow(
                    signal=indv_ccfs,
                    shifts=indv_shifts,
                    channel_combos=channel_combos,
                    num_frames=num_frames
                )
                save_plots(mean_ccf_plots, im_save_path)

                # save the mean CCF values for the file
                mean_ccf_values = save_mean_CCF_values_workflow(
                    channel_combos=channel_combos,
                    indv_ccfs=indv_ccfs
                )
                save_values_to_csv(mean_ccf_values, im_save_path, indv_ccfs_bool = False)
                # TODO: figure out a way so that the code is not hard coded to the indv vs mean CCFs
            
            # plot the individual ACF figures for the file
            if plot_ind_ACFs:
                ind_acf_plots = processor.plot_indv_acfs()
                ind_acf_path = os.path.join(im_save_path, 'Individual_ACF_plots')
                check_and_make_save_path(ind_acf_path)
                save_plots(ind_acf_plots, ind_acf_path)

            # plot the individual peak properties figures for the file
            if plot_ind_peaks:        
                ind_peak_plots = plot_indv_peak_props_workflow(
                    num_channels=num_channels,
                    num_bins=num_bins,
                    bin_values=bin_values,
                    analysis_type=analysis_type,
                    acfs=indv_acfs,
                    periods=indv_periods,
                    num_frames=num_frames
                )
                ind_peak_path = os.path.join(im_save_path, 'Individual_peak_plots')
                check_and_make_save_path(ind_peak_path)
                save_plots(ind_peak_plots, ind_peak_path)
                
            # plot the individual CCF figures for the file
            if plot_ind_CCFs and processor.num_channels > 1:
                if processor.num_channels == 1:
                    log_params['Miscellaneous'] = f'CCF plots were not generated for {file_name} because the image only has one channel'

                ind_ccf_plots = plot_indv_ccfs_workflow(
                    num_bins=num_bins,
                    bin_values=bin_values,
                    analysis_type=analysis_type,
                    channel_combos=channel_combos,
                    indv_shifts=indv_shifts,
                    indv_ccfs=indv_ccfs,
                    num_frames=num_frames
                )
                ind_ccf_plots_path = os.path.join(im_save_path, 'Individual_CCF_plots')
                check_and_make_save_path(ind_ccf_plots_path)
                save_plots(ind_ccf_plots, ind_ccf_plots_path)

                # save the individual CCF values for the file
                ind_ccf_values = save_indv_ccfs_workflow(
                    indv_ccfs=indv_ccfs,
                    channel_combos=channel_combos,
                    bin_values=bin_values,
                    analysis_type=analysis_type,
                    num_bins=num_bins
                )
                ind_ccf_val_path = os.path.join(im_save_path, 'Individual_CCF_values')
                check_and_make_save_path(ind_ccf_val_path)
                save_values_to_csv(ind_ccf_values, ind_ccf_val_path, indv_ccfs_bool = True)
                # TODO: figure out a way so that the code is not hard coded to the indv vs mean CCFs
















            ##################################################################################

            # calculate the population signal properties
            processor.calc_indv_ACFs(peak_thresh = acf_peak_thresh)
            processor.calc_indv_peak_props()
            if processor.num_channels > 1:
                processor.calc_indv_CCFs()

            # create a subfolder within the main save path with the same name as the image file
            im_save_path = os.path.join(main_save_path, name_wo_ext)
            check_and_make_save_path(im_save_path)

            # plot and save the mean autocorrelation, crosscorrelation, and peak properties for each channel
            if plot_summary_ACFs:
                mean_acf_plots = processor.plot_mean_ACF()
                save_plots(mean_acf_plots, im_save_path)

            if plot_summary_CCFs:
                mean_ccf_plots = processor.plot_mean_CCF()
                save_plots(mean_ccf_plots, im_save_path)

                #save the mean CCF values to a csv file
                mean_ccf_values = processor.save_mean_CCF_values()
                save_values_to_csv(mean_ccf_values, im_save_path, indv_ccfs_bool = False)
                # TODO: figure out a way so that the code is not hard coded to the indv vs mean CCFs


            if plot_summary_peaks:
                mean_peak_plots = processor.plot_mean_peak_props()
                save_plots(mean_peak_plots, im_save_path)
            
            # plot and save the individual autocorrelation, crosscorrelation, and peak properties for each bin in channel
            if plot_ind_peaks:        
                ind_peak_plots = processor.plot_indv_peak_props()
                ind_peak_path = os.path.join(im_save_path, 'Individual_peak_plots')
                check_and_make_save_path(ind_peak_path)
                save_plots(ind_peak_plots, ind_peak_path)
                
            if plot_ind_ACFs:
                ind_acf_plots = processor.plot_indv_acfs()
                ind_acf_path = os.path.join(im_save_path, 'Individual_ACF_plots')
                check_and_make_save_path(ind_acf_path)
                save_plots(ind_acf_plots, ind_acf_path)

            if plot_ind_CCFs and processor.num_channels > 1:
                if processor.num_channels == 1:
                    log_params['Miscellaneous'] = f'CCF plots were not generated for {file_name} because the image only has one channel'

                ind_ccf_plots = processor.plot_indv_ccfs()
                ind_ccf_plots_path = os.path.join(im_save_path, 'Individual_CCF_plots')
                check_and_make_save_path(ind_ccf_plots_path)
                save_plots(ind_ccf_plots, ind_ccf_plots_path)

                #save the indv CCF values to a csv file
                ind_ccf_values = processor.save_indv_ccf_values()
                ind_ccf_val_path = os.path.join(im_save_path, 'Individual_CCF_values')
                check_and_make_save_path(ind_ccf_val_path)
                save_values_to_csv(ind_ccf_values, ind_ccf_val_path, indv_ccfs_bool = True)
                # TODO: figure out a way so that the code is not hard coded to the indv vs mean CCFs
                
            # Summarize the data for current image as dataframe, and save as .csv
            im_measurements_df = processor.organize_measurements()
            im_measurements_df.to_csv(f'{im_save_path}/{name_wo_ext}_measurements.csv', index = False)  # type: ignore

            # generate summary data for current image
            im_summary_dict = processor.summarize_image(
                file_name=file_name, 
                group_name=group_name
                )

            # populate column headers list with keys from the measurements dictionary
            for key in im_summary_dict.keys(): 
                if key not in col_headers: 
                    col_headers.append(key) 
        
            # append summary data to the summary list
            summary_list.append(im_summary_dict)

            # useless progress bar to force completion of previous bars
            with tqdm(total = 10, miniters = 1) as dummy_pbar:
                dummy_pbar.set_description('cleanup:')
                for i in range(10):
                    dummy_pbar.update(1)

            pbar.update(1)

        # create dataframe from summary list, then sort and save the summary to a csv file
        summary_df = pd.DataFrame(summary_list, columns=col_headers)
        summary_df = summary_df.sort_values('File Name', ascending=True)
        summary_df.to_csv(f"{main_save_path}/!{now.strftime('%Y%m%d%H%M')}_summary.csv", index = False)

        if group_names != ['']:
            # generate comparisons between each group
            mean_parameter_figs = generate_group_comparison(
                summary_df = summary_df, 
                log_params = log_params
                )
            group_plots_save_path = os.path.join(main_save_path, "!group_comparison_graphs")
            check_and_make_save_path(group_plots_save_path)
            save_plots(mean_parameter_figs, group_plots_save_path)

            # save the means each parameter for the attributes to make them easier to work with in prism
            parameter_tables_dict = save_parameter_means_to_csv(
                summary_df=summary_df,
                group_names=group_names
                )
            
            mean_measurements_save_path = os.path.join(main_save_path, "!mean_parameter_measurements")
            check_and_make_save_path(mean_measurements_save_path)
            for filename, table in parameter_tables_dict.items():
                table.to_csv(f"{mean_measurements_save_path}/{filename}", index = False)

        # performance tracker end
        end = timeit.default_timer()

        # log parameters and errors
        log_params["Time Elapsed"] = f"{end - start:.2f} seconds"
        make_log(main_save_path, log_params)

        return summary_df # only here for testing for now