(function exposeSafeMarkdown(global) {
  "use strict";

  function appendInline(parent, value) {
    const text = String(value ?? "");
    let cursor = 0;

    while (cursor < text.length) {
      const boldStart = text.indexOf("**", cursor);
      const codeStart = text.indexOf("`", cursor);
      const candidates = [boldStart, codeStart].filter((position) => position >= 0);
      if (!candidates.length) {
        parent.append(document.createTextNode(text.slice(cursor)));
        return;
      }

      const markerStart = Math.min(...candidates);
      if (markerStart > cursor) {
        parent.append(document.createTextNode(text.slice(cursor, markerStart)));
      }

      const isBold = markerStart === boldStart;
      const marker = isBold ? "**" : "`";
      const contentStart = markerStart + marker.length;
      const markerEnd = text.indexOf(marker, contentStart);
      if (markerEnd < 0 || markerEnd === contentStart) {
        parent.append(document.createTextNode(text.slice(markerStart)));
        return;
      }

      const element = document.createElement(isBold ? "strong" : "code");
      element.textContent = text.slice(contentStart, markerEnd);
      parent.append(element);
      cursor = markerEnd + marker.length;
    }
  }

  function render(target, markdown) {
    const fragment = document.createDocumentFragment();
    let activeList = null;
    let activeListTag = null;

    String(markdown ?? "")
      .replaceAll("\r\n", "\n")
      .split("\n")
      .forEach((rawLine) => {
        const line = rawLine.trim();
        if (!line) {
          activeList = null;
          activeListTag = null;
          return;
        }

        const unordered = line.match(/^[-*]\s+(.+)$/);
        const ordered = line.match(/^\d+[.)]\s+(.+)$/);
        const listMatch = unordered || ordered;
        if (listMatch) {
          const listTag = unordered ? "ul" : "ol";
          if (!activeList || activeListTag !== listTag) {
            activeList = document.createElement(listTag);
            activeListTag = listTag;
            fragment.append(activeList);
          }
          const item = document.createElement("li");
          appendInline(item, listMatch[1]);
          activeList.append(item);
          return;
        }

        activeList = null;
        activeListTag = null;
        const paragraph = document.createElement("p");
        appendInline(paragraph, line.replace(/^#{1,6}\s+/, ""));
        fragment.append(paragraph);
      });

    target.replaceChildren(fragment);
  }

  global.SoniaMarkdown = Object.freeze({ render });
})(window);
