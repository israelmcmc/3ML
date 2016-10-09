import numpy as np
from threeML.utils.stats_tools import Significance
from threeML.io.progress_bar import progress_bar


class NotEnoughData(RuntimeError):
    pass


class Rebinner(object):
    """
    A class to rebin vectors keeping a minimum value per bin. It supports array with a mask, so that elements excluded
    through the mask will not be considered for the rebinning

    """
    def __init__(self, vector_to_rebin_on, min_value_per_bin, mask=None):

        # Basic check that it is possible to do what we have been requested to do

        total = np.sum(vector_to_rebin_on)

        if total < min_value_per_bin:
            raise NotEnoughData("Vector total is %s, cannot rebin at %s per bin" % (total, min_value_per_bin))

        # Check if we have a mask, if not prepare a empty one
        if mask is not None:

            mask = np.array(mask, bool)

            assert mask.shape[0] == len(vector_to_rebin_on), "The provided mask must have the same number of " \
                                                             "elements as the vector to rebin on"

        else:

            mask = np.ones_like(vector_to_rebin_on, dtype=bool)

        self._mask = mask

        # Rebin taking the mask into account

        self._starts = []
        self._stops = []
        n = 0
        bin_open = False

        for index, b in enumerate(vector_to_rebin_on):

            if not mask[index]:

                # This element is excluded by the mask

                if not bin_open:

                    # Do nothing
                    continue

                else:

                    # We need to close the bin here
                    self._stops.append(index)
                    n = 0
                    bin_open = False

            else:

                # This element is included by the mask

                if not bin_open:
                    # Open a new bin
                    bin_open = True

                    self._starts.append(index)
                    n = 0

                # Add the current value to the open bin

                n += b

                # If we are beyond the requested value, close the bin

                if n >= min_value_per_bin:
                    self._stops.append(index + 1)

                    n = 0

                    bin_open = False

        # At the end of the loop, see if we left a bin open, if we did, close it

        if bin_open:
            self._stops.append(len(vector_to_rebin_on))

        assert len(self._starts) == len(self._stops), "This is a bug: the starts and stops of the bins are not in " \
                                                      "equal number"

        self._min_value_per_bin = min_value_per_bin

    @property
    def n_bins(self):
        """
        Returns the number of bins defined.

        :return:
        """

        return len(self._starts)

    def rebin(self, *vectors):

        rebinned_vectors = []

        for vector in vectors:

            assert len(vector) == len(self._mask), "The vector to rebin must have the same number of elements of the" \
                                                   "original (not-rebinned) vector"

            # Transform in array because we need to use the mask
            vector_a = np.array(vector)

            rebinned_vector = []

            for low_bound, hi_bound in zip(self._starts, self._stops):

                rebinned_vector.append(np.sum(vector_a[low_bound:hi_bound]))

            # Vector might not contain counts, so we use a relative comparison to check that we didn't miss
            # anything

            assert abs(np.sum(rebinned_vector) / np.sum(vector_a[self._mask]) - 1) < 1e-4

            rebinned_vectors.append(np.array(rebinned_vector))

        return rebinned_vectors

    def rebin_errors(self, *vectors):
        """
        Rebin errors by summing the squares

        Args:
            *vectors:

        Returns:
            array of rebinned errors

        """

        rebinned_vectors = []

        for vector in vectors: # type: np.ndarray[np.ndarray]

            assert len(vector) == len(self._mask), "The vector to rebin must have the same number of elements of the" \
                                                   "original (not-rebinned) vector"

            rebinned_vector = []

            for low_bound, hi_bound in zip(self._starts, self._stops):

                rebinned_vector.append(np.sqrt(np.sum(vector[low_bound:hi_bound] ** 2)))

            rebinned_vectors.append(np.array(rebinned_vector))

        return rebinned_vectors

    def get_new_start_and_stop(self, old_start, old_stop):

        assert len(old_start) == len(self._mask) and len(old_stop) == len(self._mask)

        new_start = np.zeros(len(self._starts))
        new_stop = np.zeros(len(self._starts))

        for i, (low_bound, hi_bound) in enumerate(zip(self._starts, self._stops)):
            new_start[i] = old_start[low_bound]
            new_stop[i] = old_stop[hi_bound-1]

        return new_start, new_stop

    # def save_active_measurements(self, mask):
    #     """
    #     Saves the set active measurements so that they can be restored if the binning is reset.
    #
    #
    #     Returns:
    #         none
    #
    #     """
    #
    #     self._saved_mask = mask
    #     self._saved_idx = np.array(slice_disjoint((mask).nonzero()[0])).T
    #
    # @property
    # def saved_mask(self):
    #
    #     return self._saved_mask
    #
    # @property
    # def saved_selection(self):
    #
    #     return self._saved_idx
    #
    # @property
    # def min_counts(self):
    #
    #     return self._min_value_per_bin
    #
    # @property
    # def edges(self):
    #
    #     # return the low and high bins
    #     return np.array(self._edges[:-1]) + 1, np.array(self._edges[1:])


class TemporalBinner(object):
    """
    A class to provide binning of temporal light curves via various methods

    """

    def __init__(self, arrival_times):

        self._arrival_times = arrival_times

    @property
    def bins(self):

        return [self._starts, self._stops]

    @property
    def text_bins(self):

        txt_bins = []

        for start, stop in zip(self._starts, self._stops):

            txt_bins.append("%f-%f" % (start, stop))

        return txt_bins

    def bin_by_significance(self, background_getter, background_error_getter=None, sigma_level=10, min_counts=1):
        """

        Bin the data to a given significance level for a given background method and sigma
        method

        :param background_error_getter: 
        :param min_counts: 
        :param sigma_level:
        :param background_getter:
        :return:
        """

        self._starts = []

        self._stops = []

        total_counts = 0
        current_start = self._arrival_times[0]

        with progress_bar(len(self._arrival_times)) as p:
            for i, time in enumerate(self._arrival_times):

                total_counts += 1

                if total_counts < min_counts:

                    continue

                else:

                    # first use the background function to know the number of background counts
                    bkg = background_getter(current_start, time)

                    sig = Significance(total_counts, bkg)

                    if background_error_getter is not None:

                        bkg_error = background_error_getter(current_start, time)

                        sigma = sig.li_and_ma_equivalent_for_gaussian_background(bkg_error)[0]




                    else:

                        sigma = sig.li_and_ma()[0]

                    # now test if we have enough sigma



                    if sigma >= sigma_level:

                        self._stops.append(time)

                        self._starts.append(current_start)

                        current_start = time

                        total_counts = 0

                p.increase()

    def bin_by_constanst(self, dt):
        """
        Create bins with a constant dt

        :param dt: temporal spacing of the bins
        :return: None
        """

        tmp = np.arange(self._arrival_times[0], self._arrival_times[-1], dt)
        self._starts = tmp
        self._stops = tmp + dt

    def bin_by_bayesian_blocks(self, p0):

        raise NotImplementedError('Bayesian blocks is not implemented yet')
