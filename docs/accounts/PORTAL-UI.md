# Portal page shell and shared styles

Every portal page looks the same because they share one shell and one stylesheet. Keep it that way: a page supplies its content, not its own look.

## Files

- `subsystems/accounts/portal/templates/base.html`: the shell. It loads `/users/pivault.css`, puts the brand row (the keyhole mark and "KotiBot", linking to the launcher) at the top of every page, and holds the content area.
- `subsystems/accounts/portal/static/portal/pivault.css`: the palette, type, spacing, and every component (buttons, form controls, the segmented choice control, notices, tables, the wizard). It is served by the route `users/pivault.css` in `app/urls.py` without a session, like the browser scripts.
- `subsystems/accounts/portal/tests/test_stylesheet.py`: checks that the route serves CSS, that the base template loads the stylesheet, and that no page declares its own `<style>` or its own `<main>`.

## Writing a page

- Start the template with `{% extends "base.html" %}`.
- Set `{% block title %}`, `{% block heading %}` (one `<h1>`), and `{% block content %}`. Put page scripts in `{% block scripts %}`.
- Do not add a `<style>` block, a `<main>`, a back link, or a second brand row.
- Use the shared classes: `.btn` for every action (including links that act as buttons), `.role` (account role) or `.choices` (one option out of several) for a segmented choice, `.notice` for messages, and `h2` for section headings with their divider.
- A new component goes in `pivault.css`, not in a template.

## Deploying changes

Templates and `pivault.css` ship in the portal image. Deploy them with the installer from `main`, as in `claude/machines.md`. The launcher's `deploy/stack/homepage/custom.css` is a separate file and is copied by hand (`deploy/stack/homepage/README.md`).
