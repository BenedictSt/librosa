#!/usr/bin/env python
'''
CREATED:2013-02-12 16:33:40 by Brian McFee <brm2132@columbia.edu>

Beat tracking with HPSS filtering

Usage:

./hpss_beats.py input_audio.mp3 output_beats.csv

'''

import sys
import librosa
import numpy, scipy.ndimage

SR  = 22050
HOP = 64
FFT = 2048

# Load the file
print 'Loading file ... ',
(y, sr) = librosa.load(sys.argv[1], sr=SR)
print 'done.'

# Construct log-amplitude spectrogram
print 'Harmonic-percussive separation ... ',
S = librosa.feature.melspectrogram(y, sr, FFT, hop_length=HOP, n_mels=128)**0.5

# Do HPSS
(H, P) = librosa.hpss.hpss_median(S, p=4.0)
print 'done.'

# Construct onset envelope from percussive component
print 'Beat tracking ... ',

O = librosa.beat.onset_strength(S=P)

# Use LoG(P) for the onset profile
# O = numpy.mean(scipy.ndimage.gaussian_laplace(P, [1.0, 0.0]), axis=0)

# Track the beats
(bpm, beats) = librosa.beat.beat_track(onsets=O, sr=sr, hop_length=HOP)
print 'done.'

# Save the output
librosa.output.segment_csv(sys.argv[2], beats, sr, HOP)
