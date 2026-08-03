from flask import jsonify, request


def register_activity_routes(app, context):
    activity_log = context['activity_log']
    age_text = context.get('age_text')
    categories = {'all', 'automation', 'security', 'system', 'users'}

    @app.get('/api/activities/recent')
    def api_activities_recent():
        try:
            limit = int(
                request.args.get('limit', 12) or 12
            )
        except Exception:
            limit = 12

        limit = max(1, min(50, limit))

        try:
            from_hours = float(
                request.args.get(
                    'from_hours',
                    request.args.get('hours', 0),
                ) or 0
            )
        except Exception:
            from_hours = 0

        from_hours = max(
            0,
            min(168, from_hours),
        )

        try:
            to_hours = float(
                request.args.get('to_hours', 0) or 0
            )
        except Exception:
            to_hours = 0

        to_hours = max(
            0,
            min(167, to_hours),
        )

        if (
            from_hours > 0 and
            to_hours >= from_hours
        ):
            to_hours = max(
                0,
                from_hours - 1,
            )

        try:
            before_ts = float(
                request.args.get('before', 0) or 0
            )
        except Exception:
            before_ts = 0

        before_ts = max(0, before_ts)
        category = str(
            request.args.get('category', 'all') or 'all'
        ).strip().lower()

        if category not in categories:
            category = 'all'

        page = activity_log.recent_page(
            limit=limit,
            age_text=age_text,
            from_hours=from_hours,
            to_hours=to_hours,
            category=category,
            before_ts=before_ts,
        )

        return jsonify({
            'ok': True,
            **page,
        })

    return {
        'activity_log': activity_log,
    }