// @author rubenwardy
// @license magnet:?xt=urn:btih:1f739d935676111cfff4b4693e3816e664797050&dn=gpl-3.0.txt GPL-v3-or-Later

"use strict";

addEventListener("load", () => {
	const downloadCard = document.getElementById("download-card");
	downloadCard.classList.remove("d-none");

	const downloadNoJS = document.getElementById("download-nojs");
	downloadNoJS.classList.add("d-none");

	const luantiVersion = document.getElementById("luanti-version");
	luantiVersion.addEventListener("change", () => {
		setLuantiVersion(luantiVersion.selectedOptions[0]);
	});

	const luantiVersionId = localStorage.getItem("luanti-version");
	if (luantiVersionId && document.querySelector(`#luanti-version option[value='${luantiVersionId}']`)) {
		luantiVersion.value = luantiVersionId;
	}
	setLuantiVersion(luantiVersion.selectedOptions[0]);
});

function setLuantiVersion(version) {
	if (!version) {
		return;
	}

	localStorage.setItem("luanti-version", version.value);

	const {
		packageName,
		releaseId,
		releaseName,
		releaseUrl,
		releaseSize,
		releaseCreatedAt,
		latest,
	} = version.dataset;

	const success = document.getElementById("download-success");
	const noRelease = document.getElementById("download-no-release");
	const newerLuanti = document.getElementById("download-newer-luanti");
	if (latest) {
		newerLuanti.classList.add("d-none");
	} else {
		newerLuanti.classList.remove("d-none");
	}

	if (releaseName) {
		success.classList.remove("d-none");
		noRelease.classList.add("d-none");

		const btn = document.querySelector("#download-card .btn-download");
		btn.setAttribute("href", releaseUrl);

		// See PackageRelease.get_download_filename()
		const filename = `${packageName}_${releaseId}.zip`;
		btn.setAttribute("download", filename);

		const size = document.getElementById("download-file-size");
		if (releaseSize > 1024*1024) {
			size.textContent = `[${(releaseSize / 1024 / 1024).toFixed(1)} MB]`;
		} else {
			size.textContent = `[${(releaseSize / 1024).toFixed(0)} KB]`;
		}

		const info = document.getElementById("download-release-info");
		info.textContent = info.dataset.releaseText
			.replace("@1", releaseName)
			.replace("@2", releaseCreatedAt);
	} else {
		success.classList.add("d-none");
		noRelease.classList.remove("d-none");
	}
}
