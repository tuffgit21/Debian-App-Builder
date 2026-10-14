const VERSION_TEXT = "v3.0";
const VERSION_DATE = "18 Sep 2026";

const updateVersionText = () => {
  const versionSelectors = [
    "#version",
    "#versions",
    ".version",
    ".versions",
    "[id='version']",
    "[id='versions']",
  ];

  const dateSelectors = [
    "#vdate",
    "#date",
    ".vdate",
    ".date",
    "[id='vdate']",
    "[id='date']",
  ];

  const updateMatchingElements = (selectors, value) => {
    const elements = new Set();

    selectors.forEach((selector) => {
      document.querySelectorAll(selector).forEach((element) => {
        elements.add(element);
      });
    });

    elements.forEach((element) => {
      element.textContent = value;
    });
  };

  updateMatchingElements(versionSelectors, VERSION_TEXT);
  updateMatchingElements(dateSelectors, VERSION_DATE);
};

const revealCards = () => {
  const cards = document.querySelectorAll(".card.reveal");

  cards.forEach((card, index) => {
    card.classList.remove("in");
    requestAnimationFrame(() => {
      setTimeout(() => {
        card.classList.add("in");
      }, index * 80);
    });
  });
};

const initializePage = () => {
  updateVersionText();
  revealCards();
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initializePage, { once: true });
} else {
  initializePage();
}
