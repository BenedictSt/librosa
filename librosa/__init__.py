#!/usr/bin/env python
'''
CREATED:2012-10-20 11:09:30 by Brian McFee <brm2132@columbia.edu>

Top-level class for librosa

Includes constants, core utility functions, etc

'''

import numpy, numpy.fft
import scipy, scipy.signal
import os.path
import audioread

# And all the librosa sub-modules
import beat, framegenerator, chroma, tf_agc, output, hpss


#-- CORE ROUTINES --#
def load(path, target_sr=22050, mono=True):
    '''
    Load an audio file into a single, long time series

    Input:
        path:       path to the input file
        target_sr:  target sample rate      | default: 22050 
                                            | specify None to use the file's native sampling rate
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
        D[:,i]      = t[:n_specbins].conj()
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
        ft              = d[:, b/hop_length]
        ft              = numpy.concatenate((ft.conj(), ft[-2:0:-1] ), 0)

        # axis=0 to force numpy.fft to work along the correct axis.
        px              = numpy.fft.ifft(ft, axis=0).real
        x[b:(b+n_fft)]  = x[b:(b+n_fft)] + window * px[:,0]
        pass

    return x

# Dead-simple mel spectrum conversion
def hz_to_mel(f, htk=False):
    #     TODO:   2012-11-27 11:28:43 by Brian McFee <brm2132@columbia.edu>
    #  too many magic numbers in these functions
    #   redo with informative variable names
    #   then make them into parameters
    '''
    Convert Hz to Mels

    Input:
        f:      scalar or array of frequencies
        htk:    use HTK mel conversion instead of Slaney            | False 

    Output:
        m:      input frequencies f in Mels
    '''

    if numpy.isscalar(f):
        f = numpy.array([f],dtype=float)
        pass
    if htk:
        return 2595.0 * numpy.log10(1.0 + f / 700.0)
    else:
        f           = f.astype(float)
        # Oppan Slaney style
        f_0         = 0.0
        f_sp        = 200.0 / 3
        brkfrq      = 1000.0
        brkpt       = (brkfrq - f_0) / f_sp
        logstep     = numpy.exp(numpy.log(6.4) / 27.0)
        linpts      = f < brkfrq

        nlinpts     = numpy.invert(linpts)

        z           = numpy.zeros_like(f)
        # Fill in parts separately
        z[linpts]   = (f[linpts] - f_0) / f_sp
        z[nlinpts]  = brkpt + numpy.log(f[nlinpts] / brkfrq) / numpy.log(logstep)
        return z
    pass

def mel_to_hz(z, htk=False):
    if numpy.isscalar(z):
        z = numpy.array([z], dtype=float)
        pass
    if htk:
        return 700.0 * (10.0**(z / 2595.0) - 1.0)
    else:
        z           = z.astype(float)
        f_0         = 0.0
        f_sp        = 200.0 / 3
        brkfrq      = 1000
        brkpt       = (brkfrq - f_0) / f_sp
        logstep     = numpy.exp(numpy.log(6.4) / 27.0)
        f           = numpy.zeros_like(z)
        linpts      = z < brkpt
        nlinpts     = numpy.invert(linpts)

        f[linpts]   = f_0 + f_sp * z[linpts]
        f[nlinpts]  = brkfrq * numpy.exp(numpy.log(logstep) * (z[nlinpts]-brkpt))
        return f
    pass

# Stolen from ronw's chroma.py
# https://github.com/ronw/frontend/blob/master/chroma.py
def hz_to_octs(frequencies, A440=440.0):
    '''
    Convert frquencies (Hz) to octave numbers

    Input:
        frequencies:    scalar or vector of frequencies
        A440:           frequency of A440 (in Hz)                   | 440.0

    Output:
        octaves:        octave number fore each frequency
    '''
    return numpy.log2(frequencies / (A440 / 16.0))



def dctfb(nfilts, d):
    '''
    Build a discrete cosine transform basis

    Input:
        nfilts  :       number of output components
        d       :       number of input components

    Output:
        D       :       nfilts-by-d DCT matrix
    '''
    DCT = numpy.empty((nfilts, d))

    q = numpy.arange(1, 2*d, 2) * numpy.pi / (2.0 * d)
    DCT[0,:] = 1.0 / numpy.sqrt(d)
    for i in xrange(1,nfilts):
        DCT[i,:] = numpy.cos(i*q) * numpy.sqrt(2.0/d)
        pass

    return DCT 


def mfcc(S, d=20):
    '''
    Mel-frequency cepstral coefficients

    Input:
        S   :   k-by-n      log-amplitude Mel spectrogram
        d   :   number of MFCCs to return               | default: 20
    Output:
        M   :   d-by-n      MFCC sequence
    '''

    return numpy.dot(dctfb(d, S.shape[0]), S)

# Adapted from ronw's mfcc.py
# https://github.com/ronw/frontend/blob/master/mfcc.py
def melfb(sr, nfft, nfilts=40, width=1.0, fmin=0.0, fmax=None, use_htk=False):
    """Create a Filterbank matrix to combine FFT bins into Mel-frequency bins.

    Parameters
    ----------
    sr : int
        Sampling rate of the incoming signal.
    nfft : int
        FFT length to use.
    nfilts : int
        Number of Mel bands to use.  Defaults to 40.
    width : float
        The constant width of each band relative to standard Mel. Defaults 1.0
    fmin : float
        Frequency in Hz of the lowest edge of the Mel bands. Defaults to 0.
    fmax : float
        Frequency in Hz of the upper edge of the Mel bands. Defaults
        to `sr` / 2.
    use_htk: bool
        Use HTK mels instead of Slaney's version? Defaults to false.

    """

    if fmax is None:
        fmax = sr / 2.0
        pass

    # Initialize the weights
    wts         = numpy.zeros( (nfilts, nfft) )

    # Center freqs of each FFT bin
    fftfreqs    = numpy.arange( 1 + nfft / 2, dtype=numpy.double ) / nfft * sr

    # 'Center freqs' of mel bands - uniformly spaced between limits
    minmel      = hz_to_mel(fmin, htk=use_htk)
    maxmel      = hz_to_mel(fmax, htk=use_htk)
    binfreqs    = mel_to_hz(minmel + numpy.arange(nfilts + 2, dtype=float) * (maxmel - minmel) / (nfilts+1.0), htk=use_htk)

    for i in xrange(nfilts):
        freqs       = binfreqs[range(i, i+3)]
        
        # scale by width
        freqs       = freqs[1] + width * (freqs - freqs[1])

        # lower and upper slopes for all bins
        loslope     = (fftfreqs - freqs[0]) / (freqs[1] - freqs[0])
        hislope     = (freqs[2] - fftfreqs) / (freqs[2] - freqs[1])

        # .. then intersect them with each other and zero
        wts[i,:(1 + nfft/2)]    = numpy.maximum(0, numpy.minimum(loslope, hislope))

        pass

    # Slaney-style mel is scaled to be approx constant E per channel
    enorm   = 2.0 / (binfreqs[2:nfilts+2] - binfreqs[:nfilts])
    wts     = numpy.dot(numpy.diag(enorm), wts)
    
    return wts

def melspectrogram(y, sr=22050, window_length=256, hop_length=128, mel_channels=40, htk=False, width=1):
    '''
    Compute a mel spectrogram from a time series

    Input:
        y                   =   the audio signal
        sr                  =   the sampling rate of y                      | default: 22050
        window_length       =   FFT window size                             | default: 256
        hop_length          =   hop size                                    | default: 128
        mel_channels        =   number of Mel filters to use                | default: 40
        htk                 =   use HTK mels instead of Slaney              | default: False
        width               =   width of mel bins                           | default: 1

    Output:
        S                   =   Mel amplitude spectrogram
    '''

    # Compute the STFT
    S = stft(y, sr=sr, n_fft=window_length, hann_w=window_length, hop_length=hop_length)

    # Build a Mel filter
    M = melfb(sr, window_length, nfilts=mel_channels, width=width, use_htk=htk)

    # Remove everything past the nyquist frequency
    M = M[:, :(window_length / 2  + 1)]
    
    S = numpy.dot(M, numpy.abs(S))

    return S

def logamplitude(S, amin=1e-10, gain_threshold=-80.0):
    '''
    Log-scale the amplitude of a spectrogram

    Input:
        S                   =   the input spectrogram
        amin                =   minimum allowed amplitude                   | default: 1e-10
        gain_threshold      =   minimum output value                        | default: -80 (None to disable)
    Output:
        D                   =   S in dBs
    '''

    SCALE   =   20.0
    D       =   SCALE * numpy.log10(numpy.maximum(amin, numpy.abs(S)))

    if gain_threshold is not None:
        D[D < gain_threshold] = gain_threshold
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

def feature_sync(X, F, agg=numpy.mean):
    '''
    Synchronous aggregation of a feature matrix

    Input:
        X:      d-by-T              | (dense) feature matrix (eg spectrogram, chromagram, etc)
        F:      t-vector            | (ordered) array of frame numbers
        agg:    aggregator function | default: numpy.mean

    Output:
        Y:      d-by-(<=t+1) vector
        where 
                Y[:,i] = agg(X[:, F[i-1]:F[i]], axis=1)

        In order to ensure total coverage, boundary points are added to F
    '''

    F = numpy.unique(numpy.concatenate( ([0], F, [X.shape[1]]) ))

    Y = numpy.zeros( (X.shape[0], len(F)-1) )

    lb = F[0]

    for (i, ub) in enumerate(F[1:]):
        Y[:,i] = agg(X[:, lb:ub], axis=1)
        lb = ub
        pass

    return Y

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
    #   TODO:   2012-11-07 14:05:42 by Brian McFee <brm2132@columbia.edu>
    #  maybe could be done faster by directly implementing a clipped correlate
#     result = numpy.correlate(x, x, mode='full')
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

