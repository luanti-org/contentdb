// ContentDB
// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Zenon Seth <Zenon.Seth@gmail.com>

describe("homepage", () => {
	it("loads", () => {
		cy.visit("/");
		cy.get(".navbar-brand").should("be.visible").and("have.attr", "href", "/");
		cy.get(".packagecard").should("exist");
	});
});
