import numpy as np
import pandas as pd
import scipy.signal as sig
import matplotlib.pyplot as plt
from tifffile import imread, imwrite, TiffFile

class SignalProcessor:
    
    def __init__(self, image_path, box_size, roll = False, roll_size = 0, roll_by = 0):
        self.image_path = image_path
        self.box_size = box_size
        self.image = imread(self.image_path)
        self.roll = roll
        self.roll_size = roll_size
        self.roll_by = roll_by


        # standardize image dimensions
        with TiffFile(self.image_path) as tif_file:
            metadata = tif_file.imagej_metadata
        self.num_channels = metadata.get('channels', 1)
        self.num_slices = metadata.get('slices', 1)
        self.num_frames = metadata.get('frames', 1)
        self.image = self.image.reshape(self.num_frames, 
                                        self.num_slices, 
                                        self.num_channels, 
                                        self.image.shape[-2], 
                                        self.image.shape[-1])

        # max project image stack if num_slices > 1
        if self.num_slices > 1:
            print(f'Max projecting image stack')
            self.image = np.max(self.image, axis = 1)
            self.num_slices = 1
            self.image = self.image.reshape(self.num_frames, 
                                            self.num_slices, 
                                            self.num_channels, 
                                            self.image.shape[-2], 
                                            self.image.shape[-1])
        
        # calculate number of boxes in each dimension
        self.x_dim = self.image.shape[-1]
        self.y_dim = self.image.shape[-2]
        self.x_boxes = self.x_dim // self.box_size
        self.y_boxes = self.y_dim // self.box_size
        self.num_boxes = self.x_boxes * self.y_boxes
        
        if self.roll:
            self.num_subframes = (self.num_frames - roll_size) // roll_by

        # return the time-axis means for each channel
        self.box_means = np.zeros((self.x_boxes, self.y_boxes, self.num_channels, self.num_frames))
        for channel in range(self.num_channels):
            for x in range(self.x_boxes):
                for y in range(self.y_boxes):
                    self.box_means[x, y, channel, :] = np.mean(self.image[:, 0, channel, (x*self.box_size):(x*self.box_size+self.box_size), (y*self.box_size):(y*self.box_size+self.box_size)], axis=(1,2))
        # reshape into 2D array. Shape is (channels, boxes, frames)
        self.box_means = self.box_means.reshape((self.num_boxes, self.num_channels, self.num_frames))

        # empty dictionary to fill with measurements. These will subsequently be populated by the functions
        # below and returned to the user. They will also be used by the summarizing and plotting functions.
        self.acf_results = {}
        self.ccf_results = {}
        self.peak_results = {}

    # function to return the autocorrelation of each box in the image stack for each channel
    def calc_ACF(self, peak_thresh):
        '''
        Returns a dictionary containing the channel identify and box number as keys and the
        calculated period and autocorrelation curve as a values in a tuple.
        '''
        if not self.roll:
            for channel in range(self.num_channels):
                for box_num in range(self.num_boxes):
                    # calculate full autocorrelation
                    signal = self.box_means[box_num, channel]
                    acf_curve = np.correlate(signal - signal.mean(), signal - signal.mean(), mode='full')
                    # normalize the curve
                    acf_curve = acf_curve / (self.num_frames * signal.std() ** 2)
                    peaks, _ = sig.find_peaks(acf_curve, prominence=peak_thresh)
                    # absolute difference between each peak and zero
                    peaks_abs = abs(peaks - acf_curve.shape[0]//2)
                    # if peaks were identified, pick the one closest to the center
                    if len(peaks) > 1:
                        delay = np.min(peaks_abs[np.nonzero(peaks_abs)])
                    # otherwise, return nans for both period and autocorrelation curve
                    else:
                        delay = np.nan
                        acf_curve = np.full((self.num_frames*2-1), np.nan)

                    self.acf_results[f'Ch{channel+1}_ACF_box{box_num}'] = (delay, acf_curve)

        if self.roll: 
                
            for channel in range(self.num_channels):
                for box_num in range(self.num_boxes):
                    for subframe in range(self.num_subframes):
                        # calculate full autocorrelation
                        signal = self.box_means[box_num, channel, self.roll_by*subframe : self.roll_size + self.roll_by*subframe]
                        acf_curve = np.correlate(signal - signal.mean(), signal - signal.mean(), mode='full')
                        # normalize the curve
                        acf_curve = acf_curve / (self.roll_size * signal.std() ** 2)
                        peaks, _ = sig.find_peaks(acf_curve, prominence=peak_thresh)
                        # absolute difference between each peak and zero
                        peaks_abs = abs(peaks - acf_curve.shape[0]//2)
                        # if peaks were identified, pick the one closest to the center
                        if len(peaks) > 1:
                            delay = np.min(peaks_abs[np.nonzero(peaks_abs)])
                        # otherwise, return nans for both period and autocorrelation curve
                        else:
                            delay = np.nan
                            acf_curve = np.full((self.num_frames*2-1), np.nan)

                        self.acf_results[f'Ch{channel+1}_ACF_box{box_num}_subframe{subframe}_'] = (delay, acf_curve)

        return self.acf_results
                
    # function to return the cross-correlation of each box in the image stack
    def calc_CCF(self):
        '''
        Returns a dictionary containing the box number as keys and the
        calculated shift and crosscorrelation curve as a values in a tuple.
        '''
        assert self.num_channels == 2, 'CCF only works for 2 channels'
        if not self.roll:
            for box_num in range(self.num_boxes):
                # calculate full cross-correlation (channels, boxes, frames)
                signal_1 = self.box_means[box_num, 1, :]
                signal_2 = self.box_means[box_num, 0, :]
                cc_curve = np.correlate(signal_1 - signal_1.mean(), signal_2 - signal_2.mean(), mode='full')
                # normalize the curve
                cc_curve = cc_curve / (self.num_frames * signal_1.std() * signal_2.std())
                # find the peak closes to zero
                peaks, _ = sig.find_peaks(cc_curve)
                peaks_abs = abs(peaks - cc_curve.shape[0]//2)
                delay_index = peaks[np.argmin(peaks_abs)]
                shift = delay_index - cc_curve.shape[0]//2
                self.ccf_results[f'CCF_box{box_num}'] = (shift, cc_curve)
        if self.roll:
            for subframe in range(self.num_subframes):
                for box_num in range(self.num_boxes):
                    # calculate full cross-correlation (channels, boxes, frames)
                    signal_1 = self.box_means[box_num, 1, self.roll_by*subframe : self.roll_size + self.roll_by*subframe]
                    signal_2 = self.box_means[box_num, 0, self.roll_by*subframe : self.roll_size + self.roll_by*subframe]
                    cc_curve = np.correlate(signal_1 - signal_1.mean(), signal_2 - signal_2.mean(), mode='full')
                    # normalize the curve
                    cc_curve = cc_curve / (self.num_frames * signal_1.std() * signal_2.std())
                    # find the peak closes to zero
                    peaks, _ = sig.find_peaks(cc_curve)
                    peaks_abs = abs(peaks - cc_curve.shape[0]//2)
                    delay_index = peaks[np.argmin(peaks_abs)]
                    shift = delay_index - cc_curve.shape[0]//2
                    self.ccf_results[f'CCF_box{box_num}_subframe{subframe}_'] = (shift, cc_curve)

        return self.ccf_results

    # function to return the peak properties of each box for each channel
    def calc_peaks(self): 
        '''
        Returns a dictionary containing the channel identify and box number as keys and the
        calculated peak properties as a values in a tuple (width, max, min, amp, relAmp).
        '''
        if not self.roll:
            for channel in range(self.num_channels):
                for box_num in range(self.num_boxes):
                    signal = sig.savgol_filter(self.box_means[box_num, channel], window_length = 11, polyorder = 2)
                    peaks, _ = sig.find_peaks(signal, prominence=(np.max(signal)-np.min(signal))*0.1)

                    # if peaks detected, calculate properties and return property averages. Otherwise return nans
                    if len(peaks) > 0:
                        proms, _, _ = sig.peak_prominences(signal, peaks)
                        widths, _, _, _ = sig.peak_widths(signal, peaks, rel_height=0.5)
                        mean_width = np.mean(widths, axis=0)
                        mean_max = np.mean(signal[peaks], axis = 0)
                        mean_min = np.mean(signal[peaks]-proms, axis = 0)
                        mean_amp = mean_max - mean_min
                        mean_rel_amp = mean_amp / mean_min
                        self.peak_results[f'Ch{channel+1}_box{box_num}'] = (mean_width, mean_max, mean_min, mean_amp, mean_rel_amp)
                    else:
                        self.peak_results[f'Ch{channel+1}_box{box_num}'] = (np.nan, np.nan, np.nan, np.nan, np.nan)
        
        if self.roll:
            for subframe in range(self.num_subframes):
                for channel in range(self.num_channels):
                    for box_num in range(self.num_boxes):
                        signal = sig.savgol_filter(self.box_means[box_num, channel, self.roll_by*subframe : self.roll_size + self.roll_by*subframe], window_length = 11, polyorder = 2)
                        peaks, _ = sig.find_peaks(signal, prominence=(np.max(signal)-np.min(signal))*0.1)

                        # if peaks detected, calculate properties and return property averages. Otherwise return nans
                        if len(peaks) > 0:
                            proms, _, _ = sig.peak_prominences(signal, peaks)
                            widths, _, _, _ = sig.peak_widths(signal, peaks, rel_height=0.5)
                            mean_width = np.mean(widths, axis=0)
                            mean_max = np.mean(signal[peaks], axis = 0)
                            mean_min = np.mean(signal[peaks]-proms, axis = 0)
                            mean_amp = mean_max - mean_min
                            mean_rel_amp = mean_amp / mean_min
                            self.peak_results[f'Ch{channel+1}_box{box_num}_subframe{subframe}_'] = (mean_width, mean_max, mean_min, mean_amp, mean_rel_amp)
                        else:
                            self.peak_results[f'Ch{channel+1}_box{box_num}_subframe{subframe}_'] = (np.nan, np.nan, np.nan, np.nan, np.nan)
        return self.peak_results

    # function to summarize measurments statistics by appending them to the beginning of the measurement list
    def add_stats(self, measurements: list, measurement_name: str):
        '''
        Accepts a list of measurements. Calculates the mean, median, standard deviation, and SEM,
        and append them to the beginning of the list in that order. Finally, appends the name of
        the measurement of the beginning of the list.
        '''
        meas_mean = np.nanmean(measurements)
        meas_median = np.nanmedian(measurements)
        meas_std = np.nanstd(measurements)
        meas_sem = meas_std / np.sqrt(len(measurements))
        measurements.insert(0, meas_mean)
        measurements.insert(1, meas_median)
        measurements.insert(2, meas_std)
        measurements.insert(3, meas_sem)
        measurements.insert(0, measurement_name)
        return measurements

    # function to plot a summary of the period measurements
    def plot_mean_CF(self):
        '''
        This function plots the population mean autocorrelation or crosscorrelation curve.
        It also plots a histogram and box plot of the distribution of period measurements
        (for autocorrelation curves) and the distribution of shift measurements (for crosscorrelation curves).
        '''
        def return_figure(num_points: int, arr: np.ndarray, shifts_or_periods: np.ndarray, channel: str, type_of_plot: str, type_of_measurement: str):
            '''
            Space saving function for plotting the mean autocorrelation or crosscorrelation curve.
            Returns a figure object.
            '''
            fig, ax = plt.subplot_mosaic(mosaic = '''AA
                                                     BC''')
            arr_mean = np.mean(arr, axis = 0)
            arr_std = np.std(arr, axis = 0)
            ax['A'].plot(arr_mean, color='blue')
            ax['A'].fill_between(np.arange(num_points), 
                                            arr_mean - arr_std, 
                                            arr_mean + arr_std, 
                                            color='blue', 
                                            alpha=0.2)
            ax['A'].set_title(f'{channel} Mean {type_of_plot} Curve ± Standard Deviation') 
            ax['B'].hist(shifts_or_periods)
            ax['B'].set_xlabel(f'Histogram of {type_of_measurement} values (frames)')
            ax['B'].set_ylabel('Occurances')
            ax['C'].boxplot(shifts_or_periods)
            ax['C'].set_xlabel(f'Boxplot of {type_of_measurement} values')
            ax['C'].set_ylabel(f'Measured {type_of_measurement} (frames)')
            fig.subplots_adjust(hspace=0.25, wspace=0.5)   
            plt.close(fig)
            return fig

        # num points on x-axis
        x_axis_points = self.num_frames*2 - 1
        # empty dict to fill with figures, in the event that we make more than one
        self.acf_figs = {}
        
        # populate the ACF data from each box into a single array
        if len(self.acf_results) > 0:
            ch1_acfs = np.zeros(shape=(self.num_boxes, x_axis_points))
            ch1_box_periods = np.zeros(shape=(self.num_boxes))
            for box in range(self.num_boxes):
                ch1_acfs[box] = self.acf_results[f'Ch1_ACF_box{box}'][1]
                ch1_box_periods[box] = self.acf_results[f'Ch1_ACF_box{box}'][0]
            # if channel 2 exists, do the same for it
            if self.num_channels == 2:
                ch2_acfs = np.zeros(shape=(self.num_boxes, x_axis_points))
                ch2_box_periods = np.zeros(shape=(self.num_boxes))
                for box in range(self.num_boxes):
                    ch2_acfs[box] = self.acf_results[f'Ch2_ACF_box{box}'][1]
                    ch2_box_periods[box] = self.acf_results[f'Ch2_ACF_box{box}'][0]
                
                fig2 = return_figure(x_axis_points, ch2_acfs, ch2_box_periods, 'Ch2', 'Autocorrelation', 'period')
                self.acf_figs['Ch2 ACF'] = fig2
                
        
        fig1 = return_figure(x_axis_points, ch1_acfs, ch1_box_periods, 'Ch1', 'Autocorrelation', 'period')
        self.acf_figs['Ch1 ACF'] = fig1

        if len(self.ccf_results) > 0:
            mean_ccfs = np.zeros(shape=(self.num_boxes, x_axis_points))
            box_shifts = np.zeros(shape=(self.num_boxes))
            for box in range(self.num_boxes):
                mean_ccfs[box] = self.ccf_results[f'CCF_box{box}'][1]
                box_shifts[box] = self.ccf_results[f'CCF_box{box}'][0]
            
            fig3 = return_figure(x_axis_points, mean_ccfs, box_shifts, 'Mean', 'Cross-correlation', 'shift')
            self.acf_figs['Mean CCF'] = fig3
        
        return self.acf_figs

    # function to plot a summary of the peak measurements
    def plot_peak_props(self):
        '''
        This function plots the data stored in self.peak_results.
        '''
        def return_figure(min_array: np.ndarray, max_array: np.ndarray, amp_array: np.ndarray, width_array: np.ndarray, Ch_name: str):
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2)

            labels = ["amp", "min", "max"]                                                  # labels to use
            colors = ['tab:purple', 'tab:orange', 'tab:blue']                               # colors to use
            plot_this = [min_array, max_array, amp_array]                                       # list of lists to plot
            for label, color, item in zip(labels, colors, plot_this):
                ax1.hist(item, color = color, label = label, alpha = 0.75)
            ax1.legend(loc='upper right', fontsize = 'small', ncol = 1)
            ax1.set_xlabel(f'{Ch_name} histogram of peak values')
            ax1.set_ylabel('Occurances')
            bplot = ax2.boxplot(plot_this, vert=True, patch_artist=True, labels=labels)      # boxplot object
            for patch, color in zip(bplot['boxes'], colors):                                
                patch.set_facecolor(color) 
            ax2.set_xlabel(f'{Ch_name} boxplot of peak values')
            
            ax3.hist(width_array, color = 'tab:orange', alpha = 0.75)
            ax3.set_xlabel(f'{Ch_name} histogram of peak widths')
            ax3.set_ylabel('Occurances')
            bp = ax4.boxplot(width_array, vert=True, patch_artist=True)
            bp['boxes'][0].set_facecolor('tab:orange')
            ax4.set_xlabel(f'{Ch_name} boxplot of peak widths')
            ax4.set_ylabel('Peak width (frames)')
            fig.subplots_adjust(hspace=0.25, wspace=0.5)
            plt.close(fig)
            return fig

        # empty dict to fill with figures, in the event that we make more than one
        self.peak_figs = {}
        # populate the peak data from each box into a single array
        if len(self.peak_results) > 0:
            ch1_width = np.zeros(shape=(self.num_boxes))
            ch1_max = np.zeros(shape=(self.num_boxes))
            ch1_min = np.zeros(shape=(self.num_boxes))
            ch1_amp = np.zeros(shape=(self.num_boxes))
            
            for box in range(self.num_boxes):
                ch1_width[box] = self.peak_results[f'Ch1_box{box}'][0]
                ch1_max[box] = self.peak_results[f'Ch1_box{box}'][1]
                ch1_min[box] = self.peak_results[f'Ch1_box{box}'][2]
                ch1_amp[box] = self.peak_results[f'Ch1_box{box}'][3]
            # if channel 2 exists, do the same for it
            if self.num_channels == 2:
                ch2_width = np.zeros(shape=(self.num_boxes))
                ch2_max = np.zeros(shape=(self.num_boxes))
                ch2_min = np.zeros(shape=(self.num_boxes))
                ch2_amp = np.zeros(shape=(self.num_boxes))
                for box in range(self.num_boxes):
                    ch2_width[box] = self.peak_results[f'Ch2_box{box}'][0]
                    ch2_max[box] = self.peak_results[f'Ch2_box{box}'][1]
                    ch2_min[box] = self.peak_results[f'Ch2_box{box}'][2]
                    ch2_amp[box] = self.peak_results[f'Ch2_box{box}'][3]
                
                fig2 = return_figure(ch2_min, ch2_max, ch2_amp, ch2_width, 'Ch2')
                self.peak_figs['Ch2'] = fig2

            fig1 = return_figure(ch1_min, ch1_max, ch1_amp, ch1_width, 'Ch1')
            self.peak_figs['Ch1'] = fig1
        return self.peak_figs

    # function to summarize the results in the acf_results, ccf_results, and peak_results dictionaries as a dataframe
    def summarize_results(self, file_name = None, group_name = None):
        '''
        Takes the results from the calc_ACF, calc_CCF, and calc_peaks functions and returns a dataframe.
        '''
        # initial column names
        col_names = ["Parameter", "Mean", "Median", "StdDev", "SEM"]
        for box in range(self.num_boxes):
            # add box number to column names
            col_names.append(f"Box {box}")

        # initialize lists to fill with measurements for each box and summary statistics
        if len(self.acf_results) > 0:
            ch1_period_measurements = []
            for key, value in self.acf_results.items():
                if 'Ch1' in key:
                    ch1_period_measurements.append(value[0])
            # calculate the number of boxes that didn't return a period
            periods_ch1 = [x for x in ch1_period_measurements if np.isnan(x) != True]
            ch1_pcnt_no_period = ((self.num_boxes-len(periods_ch1))/self.num_boxes)*100

            if self.num_channels == 2:
                ch2_period_measurements = []
                for key, value in self.acf_results.items():
                    if 'Ch2' in key:
                        ch2_period_measurements.append(value[0])
                # calculate the number of boxes that didn't return a period
                periods_ch2 = [x for x in ch2_period_measurements if np.isnan(x) != True]
                ch2_pcnt_no_period = ((self.num_boxes-len(periods_ch2))/self.num_boxes)*100
        
        if len(self.ccf_results) > 0:
            shift_measurements = []
            for key, value in self.ccf_results.items():
                shift_measurements.append(value[0])

        if len(self.peak_results) > 0:
            ch1_width_measurements = []
            ch1_max_measurements = []
            ch1_min_measurements = []
            ch1_amp_measurements = []
            ch1_relAmp_measurements = []
            for key, value in self.peak_results.items():
                if 'Ch1' in key:
                    ch1_width_measurements.append(value[0])
                    ch1_max_measurements.append(value[1])
                    ch1_min_measurements.append(value[2])
                    ch1_amp_measurements.append(value[3])
                    ch1_relAmp_measurements.append(value[4])
            if self.num_channels == 2:
                ch2_width_measurements = []
                ch2_max_measurements = []
                ch2_min_measurements = []
                ch2_amp_measurements = []
                ch2_relAmp_measurements = []
                for key, value in self.peak_results.items():
                    if 'Ch2' in key:
                        ch2_width_measurements.append(value[0])
                        ch2_max_measurements.append(value[1])
                        ch2_min_measurements.append(value[2])
                        ch2_amp_measurements.append(value[3])
                        ch2_relAmp_measurements.append(value[4])

        # insert Mean, Median, StdDev, and SEM into the beginning of each  list
        if len(self.acf_results) > 0:
            ch1_period_measurements = self.add_stats(ch1_period_measurements, "Ch1 Period")
            if self.num_channels == 2:
                ch2_period_measurements = self.add_stats(ch2_period_measurements, "Ch2 Period")
        
        if len(self.ccf_results) > 0:
            shift_measurements = self.add_stats(shift_measurements, "Shift")

        if len(self.peak_results) > 0:
            ch1_amp_measurements = self.add_stats(ch1_amp_measurements, "Ch1 Amplitude")
            ch1_width_measurements = self.add_stats(ch1_width_measurements, "Ch1 Width")
            ch1_max_measurements = self.add_stats(ch1_max_measurements, "Ch1 Max")
            ch1_min_measurements = self.add_stats(ch1_min_measurements, "Ch1 Min")
            ch1_relAmp_measurements = self.add_stats(ch1_relAmp_measurements, "Ch1 Relative Amplitude")
            if self.num_channels == 2:
                ch2_amp_measurements = self.add_stats(ch2_amp_measurements, "Ch2 Amplitude")
                ch2_width_measurements = self.add_stats(ch2_width_measurements, "Ch2 Width")
                ch2_max_measurements = self.add_stats(ch2_max_measurements, "Ch2 Max")
                ch2_min_measurements = self.add_stats(ch2_min_measurements, "Ch2 Min")
                ch2_relAmp_measurements = self.add_stats(ch2_relAmp_measurements, "Ch2 Relative Amplitude")

        # append the lists to the dictionary, if they exist
        self.im_measurements = pd.DataFrame(columns = col_names)
        if len(self.acf_results) > 0:
            self.im_measurements = pd.concat([self.im_measurements, pd.DataFrame([ch1_period_measurements], columns = col_names)], axis = 0)
            if self.num_channels == 2:
                self.im_measurements = pd.concat([self.im_measurements, pd.DataFrame([ch2_period_measurements], columns = col_names)], axis = 0)
        if len(self.ccf_results) > 0:
            self.im_measurements = pd.concat([self.im_measurements, pd.DataFrame([shift_measurements], columns = col_names)], axis = 0)
        if len(self.peak_results) > 0:
            self.im_measurements = pd.concat([self.im_measurements, pd.DataFrame(data=[ch1_amp_measurements,
                                                                                       ch1_width_measurements,
                                                                                       ch1_max_measurements,
                                                                                       ch1_min_measurements,
                                                                                       ch1_relAmp_measurements], columns = col_names)], axis = 0)
            if self.num_channels == 2:
                self.im_measurements = pd.concat([self.im_measurements, pd.DataFrame(data=[ch2_amp_measurements,
                                                                                       ch2_width_measurements,
                                                                                       ch2_max_measurements,
                                                                                       ch2_min_measurements,
                                                                                       ch2_relAmp_measurements], columns = col_names)], axis = 0)
 
        # empty dictionary to fill with summary statistics for the current object
        self.file_data_summary = {}
        if file_name:
            self.file_data_summary['File Name'] = file_name
        if group_name:
            self.file_data_summary['Group Name'] = group_name
        self.file_data_summary['Num Boxes'] = self.num_boxes
        if len(self.acf_results) > 0:
            self.file_data_summary['Ch1 % Zero Boxes'] = ch1_pcnt_no_period
            self.file_data_summary['Ch1 Mean Period'] = np.nanmean(ch1_period_measurements[5:])
            self.file_data_summary['Ch1 Median Period'] = np.nanmedian(ch1_period_measurements[5:])
            self.file_data_summary['Ch1 StdDev Period'] = np.nanstd(ch1_period_measurements[5:])
            self.file_data_summary['Ch1 SEM Period'] = np.nanstd(ch1_period_measurements[5:]) / np.sqrt(len(ch1_period_measurements[5:]))

            if self.num_channels == 2:
                self.file_data_summary['Ch2 % Zero Boxes'] = ch2_pcnt_no_period
                self.file_data_summary['Ch2 Mean Period'] = np.nanmean(ch2_period_measurements[5:])
                self.file_data_summary['Ch2 Median Period'] = np.nanmedian(ch2_period_measurements[5:])
                self.file_data_summary['Ch2 StdDev Period'] = np.nanstd(ch2_period_measurements[5:])
                self.file_data_summary['Ch2 SEM Period'] = np.nanstd(ch2_period_measurements[5:]) / np.sqrt(len(ch2_period_measurements[5:]))

        if len(self.ccf_results) > 0:
            self.file_data_summary['Mean Shift'] = np.nanmean(shift_measurements[5:])
            self.file_data_summary['Median Shift'] = np.nanmedian(shift_measurements[5:])
            self.file_data_summary['StdDev Shift'] = np.nanstd(shift_measurements[5:])
            self.file_data_summary['SEM Shift'] = np.nanstd(shift_measurements[5:]) / np.sqrt(len(shift_measurements[5:]))

        if len(self.peak_results) > 0:
            self.file_data_summary['Ch1 Mean Width'] = np.nanmean(ch1_width_measurements[5:])
            self.file_data_summary['Ch1 Median Width'] = np.nanmedian(ch1_width_measurements[5:])
            self.file_data_summary['Ch1 StdDev Width'] = np.nanstd(ch1_width_measurements[5:])
            self.file_data_summary['Ch1 SEM Width'] = np.nanstd(ch1_width_measurements[5:]) / np.sqrt(len(ch1_width_measurements[5:]))
            self.file_data_summary['Ch1 Mean Max'] = np.nanmean(ch1_max_measurements[5:])
            self.file_data_summary['Ch1 Median Max'] = np.nanmedian(ch1_max_measurements[5:])
            self.file_data_summary['Ch1 StdDev Max'] = np.nanstd(ch1_max_measurements[5:])
            self.file_data_summary['Ch1 SEM Max'] = np.nanstd(ch1_max_measurements[5:]) / np.sqrt(len(ch1_max_measurements[5:]))
            self.file_data_summary['Ch1 Mean Min'] = np.nanmean(ch1_min_measurements[5:])
            self.file_data_summary['Ch1 Median Min'] = np.nanmedian(ch1_min_measurements[5:])
            self.file_data_summary['Ch1 StdDev Min'] = np.nanstd(ch1_min_measurements[5:])
            self.file_data_summary['Ch1 SEM Min'] = np.nanstd(ch1_min_measurements[5:]) / np.sqrt(len(ch1_min_measurements[5:]))
            self.file_data_summary['Ch1 Mean Amp'] = np.nanmean(ch1_amp_measurements[5:])
            self.file_data_summary['Ch1 Median Amp'] = np.nanmedian(ch1_amp_measurements[5:])
            self.file_data_summary['Ch1 StdDev Amp'] = np.nanstd(ch1_amp_measurements[5:])
            self.file_data_summary['Ch1 SEM Amp'] = np.nanstd(ch1_amp_measurements[5:]) / np.sqrt(len(ch1_amp_measurements[5:]))
            self.file_data_summary['Ch1 Mean RelAmp'] = np.nanmean(ch1_relAmp_measurements[5:])
            self.file_data_summary['Ch1 Median RelAmp'] = np.nanmedian(ch1_relAmp_measurements[5:])
            self.file_data_summary['Ch1 StdDev RelAmp'] = np.nanstd(ch1_relAmp_measurements[5:])
            self.file_data_summary['Ch1 SEM RelAmp'] = np.nanstd(ch1_relAmp_measurements[5:]) / np.sqrt(len(ch1_relAmp_measurements[5:]))
            
            if self.num_channels == 2:
                self.file_data_summary['Ch2 Mean Width'] = np.nanmean(ch2_width_measurements[5:])
                self.file_data_summary['Ch2 Median Width'] = np.nanmedian(ch2_width_measurements[5:])
                self.file_data_summary['Ch2 StdDev Width'] = np.nanstd(ch2_width_measurements[5:])
                self.file_data_summary['Ch2 SEM Width'] = np.nanstd(ch2_width_measurements[5:]) / np.sqrt(len(ch2_width_measurements[5:]))
                self.file_data_summary['Ch2 Mean Max'] = np.nanmean(ch2_max_measurements[5:])
                self.file_data_summary['Ch2 Median Max'] = np.nanmedian(ch2_max_measurements[5:])
                self.file_data_summary['Ch2 StdDev Max'] = np.nanstd(ch2_max_measurements[5:])
                self.file_data_summary['Ch2 SEM Max'] = np.nanstd(ch2_max_measurements[5:]) / np.sqrt(len(ch2_max_measurements[5:]))
                self.file_data_summary['Ch2 Mean Min'] = np.nanmean(ch2_min_measurements[5:])
                self.file_data_summary['Ch2 Median Min'] = np.nanmedian(ch2_min_measurements[5:])
                self.file_data_summary['Ch2 StdDev Min'] = np.nanstd(ch2_min_measurements[5:])
                self.file_data_summary['Ch2 SEM Min'] = np.nanstd(ch2_min_measurements[5:]) / np.sqrt(len(ch2_min_measurements[5:]))
                self.file_data_summary['Ch2 Mean Amp'] = np.nanmean(ch2_amp_measurements[5:])
                self.file_data_summary['Ch2 Median Amp'] = np.nanmedian(ch2_amp_measurements[5:])
                self.file_data_summary['Ch2 StdDev Amp'] = np.nanstd(ch2_amp_measurements[5:])
                self.file_data_summary['Ch2 SEM Amp'] = np.nanstd(ch2_amp_measurements[5:]) / np.sqrt(len(ch2_amp_measurements[5:]))
                self.file_data_summary['Ch2 Mean RelAmp'] = np.nanmean(ch2_relAmp_measurements[5:])
                self.file_data_summary['Ch2 Median RelAmp'] = np.nanmedian(ch2_relAmp_measurements[5:])
                self.file_data_summary['Ch2 StdDev RelAmp'] = np.nanstd(ch2_relAmp_measurements[5:])
                self.file_data_summary['Ch2 SEM RelAmp'] = np.nanstd(ch2_relAmp_measurements[5:]) / np.sqrt(len(ch2_relAmp_measurements[5:]))

        return self.im_measurements, self.file_data_summary

    # function to summarize the results in the acf_results, ccf_results, and peak_results from rolling analysis
    def summarize_rolling_results(self, file_name = None):
        '''
        Takes the results from the calc_ACF, calc_CCF, and calc_peaks functions, summarizes the results for each
        sub-movie as a dataframe, and returns a list of dataframes. Also generates and returns a summary dataframe 
        for the entire movie.
        '''
        # initial column names
        col_names = ["Parameter", "Mean", "Median", "StdDev", "SEM"]
        for box in range(self.num_boxes):
            # add box number to column names
            col_names.append(f"Box {box}")
            
        # initialize lists to fill with measurements for each box and summary statistics
        if len(self.acf_results) > 0:
            ch1_period_measurements = []
            ch1_pcnt_zero_measurements = []
            if self.num_channels == 2:
                ch2_period_measurements = []
                ch2_pcnt_zero_measurements = []
            for sub_frame in range(self.num_subframes):
                subframe_ch1_period_measurements = []
                for key, value in self.acf_results.items():
                    if f'subframe{sub_frame}_' in key and 'Ch1' in key:
                        subframe_ch1_period_measurements.append(value[0])
                
                # append to growing list
                ch1_period_measurements.append(subframe_ch1_period_measurements)
                # calculate the number of boxes that didn't return a period
                periods_ch1 = [x for x in subframe_ch1_period_measurements if np.isnan(x) != True]
                ch1_pcnt_no_period = ((self.num_boxes-len(periods_ch1))/self.num_boxes)*100
                ch1_pcnt_zero_measurements.append(ch1_pcnt_no_period)

                if self.num_channels == 2:
                    subframe_ch2_period_measurements = []
                    for key, value in self.acf_results.items():
                        if f'subframe{sub_frame}_' in key and 'Ch2' in key:
                            subframe_ch2_period_measurements.append(value[0])
                    
                    # append to growing list
                    ch2_period_measurements.append(subframe_ch2_period_measurements)
                    # calculate the number of boxes that didn't return a period
                    periods_ch2 = [x for x in subframe_ch2_period_measurements if np.isnan(x) != True]
                    ch2_pcnt_no_period = ((self.num_boxes-len(periods_ch2))/self.num_boxes)*100
                    ch2_pcnt_zero_measurements.append(ch2_pcnt_no_period)
        
        if len(self.ccf_results) > 0:
            shift_measurements = []
            for sub_frame in range(self.num_subframes):
                subframe_shift_measurements = []
                for key, value in self.ccf_results.items():
                    if f'subframe{sub_frame}_' in key:
                        subframe_shift_measurements.append(value[0])
                
                # append to growing list
                shift_measurements.append(subframe_shift_measurements)

        if len(self.peak_results) > 0:
            ch1_width_measurements = []
            ch1_max_measurements = []
            ch1_min_measurements = []
            ch1_amp_measurements = []
            ch1_relAmp_measurements = []
            if self.num_channels == 2:
                ch2_width_measurements = []
                ch2_max_measurements = []
                ch2_min_measurements = []
                ch2_amp_measurements = []
                ch2_relAmp_measurements = []

            for sub_frame in range(self.num_subframes):
                subframe_ch1_width_measurements = []
                subframe_ch1_max_measurements = []
                subframe_ch1_min_measurements = []
                subframe_ch1_amp_measurements = []
                subframe_ch1_relAmp_measurements = []
                if self.num_channels == 2:
                    subframe_ch2_width_measurements = []
                    subframe_ch2_max_measurements = []
                    subframe_ch2_min_measurements = []
                    subframe_ch2_amp_measurements = []
                    subframe_ch2_relAmp_measurements = []
                for key, val in self.peak_results.items():
                    if f'subframe{sub_frame}_' in key and 'Ch1' in key:
                        subframe_ch1_width_measurements.append(val[0])
                        subframe_ch1_max_measurements.append(val[1])
                        subframe_ch1_min_measurements.append(val[2])
                        subframe_ch1_amp_measurements.append(val[3])
                        subframe_ch1_relAmp_measurements.append(val[4])
                    if self.num_channels == 2:
                        if f'subframe{sub_frame}_' in key and 'Ch2' in key:
                            subframe_ch2_width_measurements.append(val[0])
                            subframe_ch2_max_measurements.append(val[1])
                            subframe_ch2_min_measurements.append(val[2])
                            subframe_ch2_amp_measurements.append(val[3])
                            subframe_ch2_relAmp_measurements.append(val[4])
                
                # append to growing list
                ch1_width_measurements.append(subframe_ch1_width_measurements)
                ch1_max_measurements.append(subframe_ch1_max_measurements)
                ch1_min_measurements.append(subframe_ch1_min_measurements)
                ch1_amp_measurements.append(subframe_ch1_amp_measurements)
                ch1_relAmp_measurements.append(subframe_ch1_relAmp_measurements)
                if self.num_channels == 2:
                    ch2_width_measurements.append(subframe_ch2_width_measurements)
                    ch2_max_measurements.append(subframe_ch2_max_measurements)
                    ch2_min_measurements.append(subframe_ch2_min_measurements)
                    ch2_amp_measurements.append(subframe_ch2_amp_measurements)
                    ch2_relAmp_measurements.append(subframe_ch2_relAmp_measurements)

        # insert Mean, Median, StdDev, and SEM into the beginning of each  list
        if len(self.acf_results) > 0:
            for subframe_list in ch1_period_measurements:
                subframe_list = self.add_stats(subframe_list, "Ch1 Period")
            if self.num_channels == 2:
                for ch2_subframe_list in ch2_period_measurements:
                    ch2_subframe_list = self.add_stats(ch2_subframe_list, "Ch2 Period")
        
        if len(self.ccf_results) > 0:
            for subframe_list in shift_measurements:
                subframe_list = self.add_stats(subframe_list, "Shift")
        
        if len(self.peak_results) > 0:
            for subframe_list in ch1_width_measurements:
                subframe_list = self.add_stats(subframe_list, "Ch1 Width")
            for subframe_list in ch1_max_measurements:
                subframe_list = self.add_stats(subframe_list, "Ch1 Max")
            for subframe_list in ch1_min_measurements:
                subframe_list = self.add_stats(subframe_list, "Ch1 Min")
            for subframe_list in ch1_amp_measurements:
                subframe_list = self.add_stats(subframe_list, "Ch1 Amp")
            for subframe_list in ch1_relAmp_measurements:
                subframe_list = self.add_stats(subframe_list, "Ch1 RelAmp")
            if self.num_channels == 2:
                for subframe_list in ch2_width_measurements:
                    subframe_list = self.add_stats(subframe_list, "Ch2 Width")
                for subframe_list in ch2_max_measurements:
                    subframe_list = self.add_stats(subframe_list, "Ch2 Max")
                for subframe_list in ch2_min_measurements:
                    subframe_list = self.add_stats(subframe_list, "Ch2 Min")
                for subframe_list in ch2_amp_measurements:
                    subframe_list = self.add_stats(subframe_list, "Ch2 Amp")
                for subframe_list in ch2_relAmp_measurements:
                    subframe_list = self.add_stats(subframe_list, "Ch2 RelAmp")

        # append the lists to the dictionary, if they exist
        self.im_measurements = {}
        subframe_measurements = []

        for subframe in range(self.num_subframes):
            subframe_data = []
            if len(self.acf_results) > 0:
                subframe_data.append(ch1_period_measurements[subframe])
                if self.num_channels == 2:
                    subframe_data.append(ch2_period_measurements[subframe])
            if len(self.ccf_results) > 0:
                subframe_data.append(shift_measurements[subframe])
            if len(self.peak_results) > 0:
                subframe_data.append(ch1_width_measurements[subframe])
                subframe_data.append(ch1_max_measurements[subframe])
                subframe_data.append(ch1_min_measurements[subframe])
                subframe_data.append(ch1_amp_measurements[subframe])
                subframe_data.append(ch1_relAmp_measurements[subframe])
                if self.num_channels == 2:
                    subframe_data.append(ch2_width_measurements[subframe])
                    subframe_data.append(ch2_max_measurements[subframe])
                    subframe_data.append(ch2_min_measurements[subframe])
                    subframe_data.append(ch2_amp_measurements[subframe])
                    subframe_data.append(ch2_relAmp_measurements[subframe])

            subframe_measurements.append(subframe_data)

        for subframe in range(self.num_subframes):
            self.im_measurements[f'subframe{subframe}'] = pd.DataFrame(np.array(subframe_measurements[subframe]).tolist(), columns = col_names)

        # empty dictionary to fill with summary statistics for the current object   
        self.file_data_summary = []

        for subframe in range(self.num_subframes):
            subframe_summary = {}
            if len(self.acf_results) > 0:
                subframe_summary['Subframe'] = subframe
                subframe_summary[f'Ch1 Mean Period'] = np.nanmean(ch1_period_measurements[subframe][5:])
                subframe_summary[f'Ch1 Median Period'] = np.nanmedian(ch1_period_measurements[subframe][5:])
                subframe_summary[f'Ch1 StdDev Period'] = np.nanstd(ch1_period_measurements[subframe][5:])
                subframe_summary[f'Ch1 SEM Period'] = np.nanstd(ch1_period_measurements[subframe][5:]) / np.sqrt(len(ch1_period_measurements[subframe][5:]))
                subframe_summary[f'Ch1 Pcnt Zero Period'] = ch1_pcnt_zero_measurements[subframe]
                
                if self.num_channels == 2:
                    subframe_summary[f'Ch2 Mean Period'] = np.nanmean(ch2_period_measurements[subframe][5:])
                    subframe_summary[f'Ch2 Median Period'] = np.nanmedian(ch2_period_measurements[subframe][5:])
                    subframe_summary[f'Ch2 StdDev Period'] = np.nanstd(ch2_period_measurements[subframe][5:])
                    subframe_summary[f'Ch2 SEM Period'] = np.nanstd(ch2_period_measurements[subframe][5:]) / np.sqrt(len(ch2_period_measurements[subframe][5:]))
                    subframe_summary[f'Ch2 Pcnt Zero Period'] = ch2_pcnt_zero_measurements[subframe]
        
            if len(self.ccf_results) > 0:
                subframe_summary['Subframe'] = subframe
                subframe_summary[f'Shift Mean'] = np.nanmean(shift_measurements[subframe][5:])
                subframe_summary[f'Shift Median'] = np.nanmedian(shift_measurements[subframe][5:])
                subframe_summary[f'Shift StdDev'] = np.nanstd(shift_measurements[subframe][5:])
                subframe_summary[f'Shift SEM'] = np.nanstd(shift_measurements[subframe][5:]) / np.sqrt(len(shift_measurements[subframe][5:]))
            
            if len(self.peak_results) > 0:
                subframe_summary['Subframe'] = subframe
                subframe_summary[f'Ch1 Mean Width'] = np.nanmean(ch1_width_measurements[subframe][5:])
                subframe_summary[f'Ch1 Median Width'] = np.nanmedian(ch1_width_measurements[subframe][5:])
                subframe_summary[f'Ch1 StdDev Width'] = np.nanstd(ch1_width_measurements[subframe][5:])
                subframe_summary[f'Ch1 SEM Width'] = np.nanstd(ch1_width_measurements[subframe][5:]) / np.sqrt(len(ch1_width_measurements[subframe][5:]))
                subframe_summary[f'Ch1 Mean Max'] = np.nanmean(ch1_max_measurements[subframe][5:])
                subframe_summary[f'Ch1 Median Max'] = np.nanmedian(ch1_max_measurements[subframe][5:])
                subframe_summary[f'Ch1 StdDev Max'] = np.nanstd(ch1_max_measurements[subframe][5:])
                subframe_summary[f'Ch1 SEM Max'] = np.nanstd(ch1_max_measurements[subframe][5:]) / np.sqrt(len(ch1_max_measurements[subframe][5:]))
                subframe_summary[f'Ch1 Mean Min'] = np.nanmean(ch1_min_measurements[subframe][5:])
                subframe_summary[f'Ch1 Median Min'] = np.nanmedian(ch1_min_measurements[subframe][5:])
                subframe_summary[f'Ch1 StdDev Min'] = np.nanstd(ch1_min_measurements[subframe][5:])
                subframe_summary[f'Ch1 SEM Min'] = np.nanstd(ch1_min_measurements[subframe][5:]) / np.sqrt(len(ch1_min_measurements[subframe][5:]))
                subframe_summary[f'Ch1 Mean Amp'] = np.nanmean(ch1_amp_measurements[subframe][5:])
                subframe_summary[f'Ch1 Median Amp'] = np.nanmedian(ch1_amp_measurements[subframe][5:])
                subframe_summary[f'Ch1 StdDev Amp'] = np.nanstd(ch1_amp_measurements[subframe][5:])
                subframe_summary[f'Ch1 SEM Amp'] = np.nanstd(ch1_amp_measurements[subframe][5:]) / np.sqrt(len(ch1_amp_measurements[subframe][5:]))
                subframe_summary[f'Ch1 Mean RelAmp'] = np.nanmean(ch1_relAmp_measurements[subframe][5:])
                subframe_summary[f'Ch1 Median RelAmp'] = np.nanmedian(ch1_relAmp_measurements[subframe][5:])
                subframe_summary[f'Ch1 StdDev RelAmp'] = np.nanstd(ch1_relAmp_measurements[subframe][5:])
                subframe_summary[f'Ch1 SEM RelAmp'] = np.nanstd(ch1_relAmp_measurements[subframe][5:]) / np.sqrt(len(ch1_relAmp_measurements[subframe][5:]))

                if self.num_channels == 2:
                    subframe_summary[f'Ch2 Mean Width'] = np.nanmean(ch2_width_measurements[subframe][5:])
                    subframe_summary[f'Ch2 Median Width'] = np.nanmedian(ch2_width_measurements[subframe][5:])
                    subframe_summary[f'Ch2 StdDev Width'] = np.nanstd(ch2_width_measurements[subframe][5:])
                    subframe_summary[f'Ch2 SEM Width'] = np.nanstd(ch2_width_measurements[subframe][5:]) / np.sqrt(len(ch2_width_measurements[subframe][5:]))
                    subframe_summary[f'Ch2 Mean Max'] = np.nanmean(ch2_max_measurements[subframe][5:])
                    subframe_summary[f'Ch2 Median Max'] = np.nanmedian(ch2_max_measurements[subframe][5:])
                    subframe_summary[f'Ch2 StdDev Max'] = np.nanstd(ch2_max_measurements[subframe][5:])
                    subframe_summary[f'Ch2 SEM Max'] = np.nanstd(ch2_max_measurements[subframe][5:]) / np.sqrt(len(ch2_max_measurements[subframe][5:]))
                    subframe_summary[f'Ch2 Mean Min'] = np.nanmean(ch2_min_measurements[subframe][5:])
                    subframe_summary[f'Ch2 Median Min'] = np.nanmedian(ch2_min_measurements[subframe][5:])
                    subframe_summary[f'Ch2 StdDev Min'] = np.nanstd(ch2_min_measurements[subframe][5:])
                    subframe_summary[f'Ch2 SEM Min'] = np.nanstd(ch2_min_measurements[subframe][5:]) / np.sqrt(len(ch2_min_measurements[subframe][5:]))
                    subframe_summary[f'Ch2 Mean Amp'] = np.nanmean(ch2_amp_measurements[subframe][5:])
                    subframe_summary[f'Ch2 Median Amp'] = np.nanmedian(ch2_amp_measurements[subframe][5:])
                    subframe_summary[f'Ch2 StdDev Amp'] = np.nanstd(ch2_amp_measurements[subframe][5:])
                    subframe_summary[f'Ch2 SEM Amp'] = np.nanstd(ch2_amp_measurements[subframe][5:]) / np.sqrt(len(ch2_amp_measurements[subframe][5:]))
                    subframe_summary[f'Ch2 Mean RelAmp'] = np.nanmean(ch2_relAmp_measurements[subframe][5:])
                    subframe_summary[f'Ch2 Median RelAmp'] = np.nanmedian(ch2_relAmp_measurements[subframe][5:])
                    subframe_summary[f'Ch2 StdDev RelAmp'] = np.nanstd(ch2_relAmp_measurements[subframe][5:])
                    subframe_summary[f'Ch2 SEM RelAmp'] = np.nanstd(ch2_relAmp_measurements[subframe][5:]) / np.sqrt(len(ch2_relAmp_measurements[subframe][5:]))

            self.file_data_summary.append(subframe_summary)
            
        # populate column headers list with keys from the measurements dictionary
        col_headers = []
        for subframe_summary in self.file_data_summary:
            for key in subframe_summary.keys(): 
                if key not in col_headers: 
                    col_headers.append(key) 
        # create dataframe from the dictionaries in file_data_summary, using the subframe key as a common index
        self.file_data_summary = pd.DataFrame(self.file_data_summary, index = [f'Subframe{subframe}' for subframe in range(self.num_subframes)], columns = col_headers)



        #self.file_data_summary = pd.DataFrame(self.file_data_summary, columns = col_headers)

        return self.im_measurements, self.file_data_summary

