/* George Pick'ems - turns emoji results into type and marks the season leader(s). */
(() => {
  const verdict = /^(.*?):\s*(?:✅|❌|🤝)\s*(Cover|Loss|Push)$/u;
  document.querySelectorAll(".pickems .result-badge-pick").forEach((el) => {
    const text = el.textContent.trim();
    const match = text.match(verdict);
    if (match) {
      const line = document.createElement("span");
      line.className = "pick-line";
      const tag = document.createElement("span");
      tag.className = `verdict is-${match[2].toLowerCase()}`;
      tag.textContent = match[2];
      line.append(match[1], tag);
      el.replaceChildren(line);
    } else if (/^(⬆️|⬇️)/u.test(text)) {
      el.textContent = text.replace(/^(⬆️|⬇️)\s*/u, "");
    }
  });

  // Only the current week's table; ties at the top all get the highlight.
  const rows = [...document.querySelectorAll(".pickems > .pickems-grid:not(.pickems-lines) tbody tr")];
  const record = (row) => row.cells[row.cells.length - 1].textContent.trim();
  rows.filter((row) => record(row) === record(rows[0])).forEach((row) => row.classList.add("is-leader"));
})();
