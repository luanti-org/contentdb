// ContentDB
// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Zenon Seth <Zenon.Seth@gmail.com>

const { defineConfig } = require("cypress");

module.exports = defineConfig({
	e2e: {
		baseUrl: "http://localhost:5123",
		supportFile: false,
	},
});
