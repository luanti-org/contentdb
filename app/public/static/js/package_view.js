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

	carouselElement.addEventListener("slide.bs.carousel", e => {
		if (videoEmbed) {
			const event = new Event("stopVideo");
			videoEmbed.dispatchEvent(event);
		}

		const previous = document.querySelector(".gallery-thumbnails a.active");
		previous.classList.remove("active");
		previous.removeAttribute("aria-current");

		const to = e.to;
		const next = document.querySelector(`.gallery-thumbnails a[data-bs-slide-to="${to}"]`);
		next.classList.add("active");
		next.setAttribute("aria-current", "true");
	});

	document.querySelectorAll("a[data-fake-click]").forEach(ele => {
		ele.addEventListener("click", e => {
			document.querySelector(ele.getAttribute("data-fake-click")).click();
			e.preventDefault();
		});
	});
});
