"""The image-provider seam: one method, implemented per backend."""

from abc import ABC, abstractmethod


class ImageProviderError(RuntimeError):
    """Raised when a provider cannot produce an edited image.

    Covers missing credentials, HTTP failures, and a response that doesn't
    carry the image data the provider's own contract promises -- callers
    only ever need to catch this one type, never a provider-specific one.
    """


class ImageProvider(ABC):
    """A backend that takes a photo plus a prompt and returns an edited image."""

    @abstractmethod
    def edit_image(self, *, image_bytes: bytes, image_filename: str, prompt: str) -> bytes:
        """Return the edited image's raw bytes.

        Args:
            image_bytes: The source photo's raw bytes.
            image_filename: The source photo's filename (extension signals
                content type to providers that care, e.g. `photo.jpg`).
            prompt: The text prompt describing the edit (see
                `prompt_builder.build_image_prompt`).

        Returns:
            The edited image's raw bytes (format is provider-dependent;
            callers sniff it rather than assuming one).

        Raises:
            ImageProviderError: If credentials are missing, the request
                fails, or the response doesn't carry image data.
        """
        raise NotImplementedError
