import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (
    REPOSITORY_ROOT / "templates",
    REPOSITORY_ROOT / "static",
    REPOSITORY_ROOT / "subsystems",
)
MARKUP_SOURCE_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".mjs",
    ".py",
    ".svg",
}
INLINE_EVENT_ATTRIBUTE = re.compile(
    r"(?i)(?<![.\w-])(?P<attribute>on[a-z][a-z0-9_-]*)\s*="
)
JAVASCRIPT_URL = re.compile(r"(?i)javascript\s*:")
EVENT_HANDLER_ATTRIBUTES = {
    "onabort", "onafterprint", "onanimationcancel", "onanimationend",
    "onanimationiteration", "onanimationstart", "onauxclick",
    "onbeforeinput", "onbeforeprint", "onbeforeunload", "onbegin",
    "onblur", "oncancel", "oncanplay", "oncanplaythrough", "onchange",
    "onclick", "onclose", "oncontextmenu", "oncopy", "oncuechange",
    "oncut", "ondblclick", "ondrag", "ondragend", "ondragenter",
    "ondragleave", "ondragover", "ondragstart", "ondrop",
    "ondurationchange", "onemptied", "onend", "onended", "onerror",
    "onfocus", "onfocusin", "onfocusout", "onformdata",
    "onfullscreenchange", "onfullscreenerror", "ongotpointercapture",
    "onhashchange", "oninput", "oninvalid", "onkeydown", "onkeypress",
    "onkeyup", "onload", "onloadeddata", "onloadedmetadata",
    "onloadstart", "onlostpointercapture", "onmessage", "onmessageerror",
    "onmousedown", "onmouseenter", "onmouseleave", "onmousemove",
    "onmouseout", "onmouseover", "onmouseup", "onoffline", "ononline",
    "onopen", "onpagehide", "onpageshow", "onpaste", "onpause",
    "onplay", "onplaying", "onpointercancel", "onpointerdown",
    "onpointerenter", "onpointerleave", "onpointermove", "onpointerout",
    "onpointerover", "onpointerup", "onpopstate", "onprogress",
    "onratechange", "onrepeat", "onreset", "onresize", "onscroll",
    "onsecuritypolicyviolation", "onseeked", "onseeking", "onselect",
    "onselectionchange", "onselectstart", "onslotchange", "onstalled",
    "onstorage", "onsubmit", "onsuspend", "ontimeupdate", "ontoggle",
    "ontouchcancel", "ontouchend", "ontouchmove", "ontouchstart",
    "ontransitioncancel", "ontransitionend", "ontransitionrun",
    "ontransitionstart", "onunhandledrejection", "onunload",
    "onvolumechange", "onwaiting", "onwheel",
}


class SourceMarkupPolicyTests(unittest.TestCase):
    @staticmethod
    def markup_sources():
        for root in SOURCE_ROOTS:
            for path in root.rglob("*"):
                if not path.is_file():
                    continue

                if path.suffix.lower() not in MARKUP_SOURCE_SUFFIXES:
                    continue

                if "vendor" in path.relative_to(REPOSITORY_ROOT).parts:
                    continue

                yield path

    def test_generated_and_static_markup_has_no_inline_script_surfaces(self):
        findings = []

        for path in self.markup_sources():
            source = path.read_text(encoding="utf-8")

            for match in INLINE_EVENT_ATTRIBUTE.finditer(source):
                attribute = match.group("attribute").lower()
                line_start = source.rfind("\n", 0, match.start()) + 1
                line_prefix = source[line_start:match.start()]

                if attribute not in EVENT_HANDLER_ATTRIBUTES:
                    continue

                if (
                    path.suffix.lower() in {".js", ".mjs"}
                    and re.search(r"\b(?:const|let|var)\s*$", line_prefix)
                ):
                    continue

                line = source.count("\n", 0, match.start()) + 1
                findings.append(
                    f"{path.relative_to(REPOSITORY_ROOT)}:{line}: "
                    "inline event attribute"
                )

            for match in JAVASCRIPT_URL.finditer(source):
                line = source.count("\n", 0, match.start()) + 1
                findings.append(
                    f"{path.relative_to(REPOSITORY_ROOT)}:{line}: "
                    "javascript URL"
                )

        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
