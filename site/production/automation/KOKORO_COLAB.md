# Kokoro narration in Google Colab

1. Create a GPU or CPU notebook.
2. Run `!pip install kokoro>=0.9.4 soundfile` and `!apt-get -qq -y install espeak-ng`.
3. Upload the repository or the selected script.
4. Run `python production/automation/synthesize_narration.py --script production/scripts/plaintext/01-why-deep-sea-creatures-look-so-weird.txt --output production/audio/narration/01-why-deep-sea-creatures-look-so-weird.wav`.
5. Audition the complete file before rendering.

Do not publish a voice file that has not passed pronunciation, clipping, pacing, and consistency review.
