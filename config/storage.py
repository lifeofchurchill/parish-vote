"""
How static files (CSS, JavaScript, images) are stored on the live server.
"""
from whitenoise.storage import CompressedManifestStaticFilesStorage


class ForgivingStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """
    WhiteNoise's storage (fingerprinted, compressed files), with one change:
    a template that mentions a file which doesn't exist gets a plain link to it
    instead of crashing the whole page.

    Why: the sign-in page links to a church photo (voting/img/church.jpg) that may not
    have been added yet. Normally that would turn the sign-in page into a "Server Error".
    With this, the browser just can't find the photo, and onerror="this.remove()" hides it.
    """

    manifest_strict = False

    def hashed_name(self, name, content=None, filename=None):
        try:
            return super().hashed_name(name, content, filename)
        except ValueError:
            # The file isn't there: use its plain name rather than raising an error
            return name