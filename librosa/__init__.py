#!/usr/bin/env python
'''
CREATED:2012-10-20 11:09:30 by Brian McFee <brm2132@columbia.edu>

Top-level class for librosa

Includes constants, core utility functions, etc

'''

import numpy, numpy.fft
import scipy.signal
import os.path
import audioread

# And all the librosa sub-modules
import librosa.beat
import librosa.feature
import librosa.hpss
import librosa.output


#-- CORE ROUTINES --#
def load(path, target_sr=22050, mono=True):
    '''
    Load an audio file into a single, long time series

    Input:
        path:       path to the input file
        target_sr:  target sample rate      | default: 22050 
                                            | specify None to use the native sampling rate
        mono:       convert to mono?        | default: True

    Output:
        y:          the time series
        sr:         the sampling rate
    '''

    with audioread.audio_open(os.path.realpath(path)) as f:
        sr = f.samplerate
        y = [numpy.frombuffer(frame, '<i2').astype(float) / float(1<<15) for frame in f]
        y = numpy.concatenate(y)
        if f.channels > 1:
            if mono:
                y = 0.5 * (y[::2] + y[1::2])
            else:
                y = y.reshape( (-1, 2)).T
                pass
            pass
        pass

    if target_sr is not None:
        return (resample(y, sr, target_sr), target_sr)

    return (y, sr)

def resample(y, orig_sr, target_sr):
    '''
    Resample a signal from orig_sr to target_sr

    Input:
        y:          time series (either mono or stereo)
        orig_sr:    original sample rate of y
        target_sr:  target sample rate
    
    Output:
        y_hat:      resampled signal
    '''

    if orig_sr == target_sr:
        return y

    axis = y.ndim-1

    n_samples = len(y) * target_sr / orig_sr

    y_hat = scipy.signal.resample(y, n_samples, axis=axis)

    return y_hat

def stft(y, sr=22050, n_fft=256, hann_w=None, hop_length=None):
    '''
    Short-time fourier transform

    Inputs:
        y           = the input signal
        sr          = sampling rate of y            | default: 22050
        n_fft       = the number of FFT components  | default: 256
        hann_w      = size of hann window           | default: = n_fft
        hop_length  = hop length                    | default: = hann_w / 2

    Output:
        D           = complex-valued STFT matrix of y
    '''
    num_samples = len(y)

    if hann_w is None:
        hann_w = n_fft
        pass

    if hann_w == 0:
        window = numpy.ones((n_fft,))
    else:
        window = pad(scipy.signal.hann(hann_w), n_fft)
        pass

    # Set the default hop, if it's not already specified
    if hop_length is None:
        hop_length = int(n_fft / 2)
        pass

    n_specbins  = 1 + int(n_fft / 2)
    n_frames    = 1 + int( (num_samples - n_fft) / hop_length)

    # allocate output array
    D = numpy.empty( (n_specbins, n_frames), dtype=numpy.complex)

    for i in xrange(n_frames):
        b           = i * hop_length
        u           = window * y[b:(b+n_fft)]
        t           = numpy.fft.fft(u)

        # Conjugate here to match phase from DPWE code
        D[:, i]     = t[:n_specbins].conj()
        pass

    return D


def istft(d, n_fft=None, hann_w=None, hop_length=None):
    '''
    Inverse short-time fourier transform

    Inputs:
        d           = STFT matrix
        n_fft       = number of FFT components          | default: 2 * (d.shape[0] -1
        hann_w      = size of hann window               | default: n_fft
        hop_length  = hop length                        | default: hann_w / 2

    Outputs:
        y       = time domain signal reconstructed from d
    '''

    # n = Number of stft frames
    n = d.shape[1]

    if n_fft is None:
        n_fft = 2 * (d.shape[0] - 1)
        pass

    if hann_w is None:
        hann_w = n_fft
        pass

    if hann_w == 0:
        window = numpy.ones(n_fft)
    else:
        # XXX:    2013-03-09 12:17:38 by Brian McFee <brm2132@columbia.edu>
        #   magic number alert!
        #   2/3 scaling is to make stft(istft(.)) identity for 25% hop
        
        window = pad(scipy.signal.hann(hann_w) * 2.0 / 3, n_fft)
        pass

    # Set the default hop, if it's not already specified
    if hop_length is None:
        hop_length = int(n_fft / 2.0 )
        pass

    x_length    = n_fft + (n - 1) * hop_length
    x           = numpy.zeros(x_length)

    for b in xrange(0, hop_length * n, hop_length):
        ft              = d[:, b/hop_length].flatten()
        ft              = numpy.concatenate((ft.conj(), ft[-2:0:-1] ), 0)

        px              = numpy.fft.ifft(ft).real
        x[b:(b+n_fft)]  = x[b:(b+n_fft)] + window * px
        pass

    return x

def logamplitude(S, amin=1e-10, gain_threshold=-80.0):
    '''
    Log-scale the amplitude of a spectrogram

    Input:
        S                   =   the input spectrogram
        amin                =   minimum allowed amplitude       | default: 1e-10
        gain_threshold      =   minimum output value            | default: -80 

    Output:
        D                   =   S in dBs
    '''

    D       =   20.0 * numpy.log10(numpy.maximum(amin, numpy.abs(S)))

    if gain_threshold is not None:
        D = numpy.maximum(D, D.max() + gain_threshold)
        pass

    return D


#-- UTILITIES --#
def frames_to_time(frames, sr=22050, hop_length=64):
    '''
    Converts frame counts to time (seconds)

    Input:
        frames:         scalar or n-by-1 vector of frame numbers
        sr:             sampling rate                               | 22050 Hz
        hop_length:     hop length of the frames                    | 64 frames

    Output:
        times:          time (in seconds) of each given frame number
    '''
    return frames * float(hop_length) / float(sr)


def pad(w, d_pad, v=0.0, center=True):
    '''
    Pad a vector w out to d dimensions, using value v

    if center is True, w will be centered in the output vector
    otherwise, w will be at the beginning
    '''
    # FIXME:  2012-11-27 11:08:54 by Brian McFee <brm2132@columbia.edu>
    #  This function will be deprecated by numpy 1.7.0    

    d = len(w)
    if d > d_pad:
        raise ValueError('Insufficient pad space')

    #     FIXME:  2013-03-09 10:07:56 by Brian McFee <brm2132@columbia.edu>
    #  slightly quicker via fill
    q = v * numpy.ones(d_pad)
    q[:d] = w

    if center:
        q = numpy.roll(q, numpy.floor((d_pad - d) / 2.0).astype(int), axis=0)
        pass
    return q

def autocorrelate(x, max_size=None):
    '''
        Bounded auto-correlation

        Input:
            x:          t-by-1  vector
            max_size:   (optional) maximum lag                  | None

        Output:
            z:          x's autocorrelation (up to max_size if given)
    '''

    result = scipy.signal.fftconvolve(x, x[::-1], mode='full')

    result = result[len(result)/2:]
    if max_size is None:
        return result
    return result[:max_size]

def localmax(x):
    '''
        Return 1 where there are local maxima in x (column-wise)
        left edges do not fire, right edges might.
    '''

    return numpy.logical_and(x > numpy.hstack([x[0], x[:-1]]), x >= numpy.hstack([x[1:], x[-1]]))

