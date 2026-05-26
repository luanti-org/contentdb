// @author rubenwardy
// @license magnet:?xt=urn:btih:1f739d935676111cfff4b4693e3816e664797050&dn=gpl-3.0.txt GPL-v3-or-Later

"use strict";

addEventListener("load", () => {
	const videoEmbed = document.querySelector("#galleryCarousel .video-embed");
	const carouselElement = document.getElementById("galleryCarousel");

	// carousel.pause() does not work properly given `pause: "hover"`, so disable
	// autoplay when there is a video embed
	const carousel = new bootstrap.Carousel(carouselElement, videoEmbed ? {} : {
		ride: "carousel",
	});

	if (videoEmbed) {
		carouselElement.addEventListener("slide.bs.carousel", () => {
			const event = new Event("stopVideo");
			videoEmbed.dispatchEvent(event);
		});
	}

	document.querySelectorAll("a[data-fake-click]").forEach(ele => {
		ele.addEventListener("click", e => {
			document.querySelector(ele.getAttribute("data-fake-click")).click();
			e.preventDefault();
		});
	});
});
