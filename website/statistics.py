from collections import namedtuple
from datetime import date
from enum import Enum

from flask import g, jsonify, request
from flask_babel import gettext

import utils
import hedy_content
import hedy
import jinja_partials
from website.flask_helpers import render_template
from website import querylog
from website.auth import is_admin, is_teacher, requires_admin, requires_login

from .database import Database
from .website_module import WebsiteModule, route

"""The Key tuple is used to aggregate the raw data by level, time or username."""
Key = namedtuple("Key", ["name", "class_"])
level_key = Key("level", int)
username_key = Key("id", str)
week_key = Key("week", str)


class UserType(Enum):
    ALL = "@all"  # Old value used before user types
    ANONYMOUS = "@all-anonymous"
    LOGGED = "@all-logged"
    STUDENT = "@all-students"


class StatisticsModule(WebsiteModule):
    def __init__(self, db: Database):
        super().__init__("stats", __name__)
        self.db = db

    @route("/stats/class/<class_id>", methods=["GET"])
    @requires_login
    def render_class_stats(self, user, class_id):
        if not is_teacher(user) and not is_admin(user):
            return utils.error_page(error=403, ui_message=gettext("retrieve_class_error"))

        class_ = self.db.get_class(class_id)
        if not class_ or (class_["teacher"] != user["username"] and not is_admin(user)):
            return utils.error_page(error=404, ui_message=gettext("no_such_class"))

        students = sorted(class_.get("students", []))
        return render_template(
            "class-stats.html",
            class_info={"id": class_id, "students": students},
            current_page="my-profile",
            page_title=gettext("title_class statistics"),
            javascript_page_options=dict(page='class-stats'),
        )

    @route("/logs/class/<class_id>", methods=["GET"])
    @requires_login
    def render_class_logs(self, user, class_id):
        if not is_teacher(user) and not is_admin(user):
            return utils.error_page(error=403, ui_message=gettext("retrieve_class_error"))

        class_ = self.db.get_class(class_id)
        if not class_ or (class_["teacher"] != user["username"] and not is_admin(user)):
            return utils.error_page(error=404, ui_message=gettext("no_such_class"))

        students = sorted(class_.get("students", []))
        return render_template(
            "class-logs.html",
            class_info={"id": class_id, "students": students},
            current_page="my-profile",
            page_title=gettext("title_class logs"),
        )

    @route("/class-stats/<class_id>", methods=["GET"])
    @requires_login
    def get_class_stats(self, user, class_id):
        start_date = request.args.get("start", default=None, type=str)
        end_date = request.args.get("end", default=None, type=str)

        cls = self.db.get_class(class_id)
        students = cls.get("students", [])
        if not cls or not students or (cls["teacher"] != user["username"] and not is_admin(user)):
            return "No such class or class empty", 403

        program_data = self.db.get_program_stats(students, start_date, end_date)
        quiz_data = self.db.get_quiz_stats(students, start_date, end_date)
        data = program_data + quiz_data

        per_level_data = _aggregate_for_keys(data, [level_key])
        per_week_data = _aggregate_for_keys(data, [week_key, level_key])
        per_level_per_student = _aggregate_for_keys(data, [username_key, level_key])
        per_week_per_student = _aggregate_for_keys(data, [username_key, week_key])

        response = {
            "class": {
                "per_level": _to_response_per_level(per_level_data),
                "per_week": _to_response(per_week_data, "week", lambda e: f"L{e['level']}"),
            },
            "students": {
                "per_level": _to_response(per_level_per_student, "level", lambda e: e["id"], _to_response_level_name),
                "per_week": _to_response(per_week_per_student, "week", lambda e: e["id"]),
            },
        }
        return jsonify(response)

    @route("/grid_overview/class/<class_id>", methods=["GET"])
    @requires_login
    def render_class_grid_overview(self, user, class_id):
        if not is_teacher(user) and not is_admin(user):
            return utils.error_page(error=403, ui_message=gettext("retrieve_class_error"))

        students, class_, class_adventures_formatted, ticked_adventures, \
            adventure_names, student_adventures = self.get_grid_info(
                user, class_id, 1)
        matrix_values = self.get_matrix_values(students, class_adventures_formatted, ticked_adventures, '1')
        adventure_names = {value: key for key, value in adventure_names.items()}

        if not class_ or (class_["teacher"] != user["username"] and not is_admin(user)):
            return utils.error_page(error=404, ui_message=gettext("no_such_class"))

        return render_template(
            "class-grid.html",
            class_info={"id": class_id, "students": students, "name": class_["name"]},
            current_page="grid_overview",
            max_level=hedy.HEDY_MAX_LEVEL,
            class_adventures=class_adventures_formatted,
            ticked_adventures=ticked_adventures,
            matrix_values=matrix_values,
            adventure_names=adventure_names,
            student_adventures=student_adventures,
            page_title=gettext("title_class grid_overview"),
        )

    @route("/grid_overview/class/<class_id>/level", methods=["GET"])
    @requires_login
    def change_dropdown_level(self, user, class_id):
        level = request.args.get('level')
        students, class_, class_adventures_formatted, ticked_adventures, \
            adventure_names, student_adventures = self.get_grid_info(
                user, class_id, level)
        matrix_values = self.get_matrix_values(students, class_adventures_formatted, ticked_adventures, level)
        adventure_names = {value: key for key, value in adventure_names.items()}

        return jinja_partials.render_partial("customize-grid/partial-grid-levels.html",
                                             level=level,
                                             class_info={"id": class_id, "students": students, "name": class_["name"]},
                                             current_page="grid_overview",
                                             max_level=hedy.HEDY_MAX_LEVEL,
                                             class_adventures=class_adventures_formatted,
                                             ticked_adventures=ticked_adventures,
                                             matrix_values=matrix_values,
                                             adventure_names=adventure_names,
                                             student_adventures=student_adventures,
                                             page_title=gettext("title_class grid_overview"),
                                             )

    @route("/grid_overview/class/<class_id>/level", methods=["POST"])
    @requires_login
    def change_checkbox(self, user, class_id):
        level = request.args.get('level')
        student_index = request.args.get('student_index', type=int)
        adventure_index = request.args.get('adventure_index', type=int)
        students, class_, class_adventures_formatted, ticked_adventures, adventure_names, _ = self.get_grid_info(
            user, class_id, level)
        matrix_values = self.get_matrix_values(students, class_adventures_formatted, ticked_adventures, level)

        adventure_names = {value: key for key, value in adventure_names.items()}
        current_adventure_name = class_adventures_formatted[level][adventure_index]
        student_adventure_id = f"{students[student_index]}-{adventure_names[current_adventure_name]}-{level}"

        self.db.update_student_adventure(student_adventure_id, matrix_values[student_index][adventure_index])
        _, _, _, ticked_adventures, _, student_adventures = self.get_grid_info(user, class_id, level)
        matrix_values[student_index][adventure_index] = not matrix_values[student_index][adventure_index]

        return jinja_partials.render_partial("customize-grid/partial-grid-levels.html",
                                             level=level,
                                             class_info={"id": class_id, "students": students, "name": class_["name"]},
                                             current_page="grid_overview",
                                             max_level=hedy.HEDY_MAX_LEVEL,
                                             class_adventures=class_adventures_formatted,
                                             ticked_adventures=ticked_adventures,
                                             adventure_names=adventure_names,
                                             student_adventures=student_adventures,
                                             matrix_values=matrix_values,
                                             page_title=gettext("title_class grid_overview"),
                                             )

    def get_matrix_values(self, students, class_adventures_formatted, ticked_adventures, level):
        rendered_adventures = class_adventures_formatted.get(level)
        matrix = [[None for _ in range(len(class_adventures_formatted[level]))] for _ in range(len(students))]
        for student_index in range(len(students)):
            student_list = ticked_adventures.get(students[student_index])
            if student_list and rendered_adventures:
                for program in student_list:
                    if program['level'] == level:
                        index = rendered_adventures.index(program['name'])
                        matrix[student_index][index] = 1 if program['ticked'] else 0
        return matrix

    @route("/program-stats", methods=["GET"])
    @requires_admin
    def get_program_stats(self, user):
        start_date = request.args.get("start", default=None, type=str)
        end_date = request.args.get("end", default=None, type=str)

        ids = [e.value for e in UserType]
        program_runs_data = self.db.get_program_stats(ids, start_date, end_date)
        quiz_data = self.db.get_quiz_stats(ids, start_date, end_date)
        data = program_runs_data + quiz_data

        per_level_data = _aggregate_for_keys(data, [level_key])
        per_week_data = _aggregate_for_keys(data, [week_key, level_key])

        response = {
            "per_level": _to_response_per_level(per_level_data),
            "per_week": _to_response(per_week_data, "week", lambda e: f"L{e['level']}"),
        }
        return jsonify(response)

    def get_grid_info(self, user, class_id, level):
        class_ = self.db.get_class(class_id)
        if hedy_content.Adventures(g.lang).has_adventures():
            adventures = hedy_content.Adventures(g.lang).get_adventure_keyname_name_levels()
        else:
            adventures = hedy_content.Adventures("en").get_adventure_keyname_name_levels()

        students = sorted(class_.get("students", []))
        teacher_adventures = self.db.get_teacher_adventures(user["username"])
        class_info = self.db.get_class_customizations(class_id)
        class_adventures = class_info.get('sorted_adventures')

        adventure_names = {}
        for adv_key, adv_dic in adventures.items():
            for name, _ in adv_dic.items():
                adventure_names[adv_key] = hedy_content.get_localized_name(name, g.keyword_lang)

        for adventure in teacher_adventures:
            adventure_names[adventure['id']] = adventure['name']

        class_adventures_formatted = {}
        for key, value in class_adventures.items():
            adventure_list = []
            for adventure in value:
                # if the adventure is not in adventure names it means that the data in the customizations is bad
                if not adventure['name'] == 'next' and adventure['name'] in adventure_names:
                    adventure_list.append(adventure_names[adventure['name']])
            class_adventures_formatted[key] = adventure_list

        ticked_adventures = {}
        student_adventures = {}
        for student in students:
            programs = self.db.last_level_programs_for_user(student, level)
            if programs:
                ticked_adventures[student] = []
                current_program = {}
                for _, program in programs.items():
                    name = adventure_names.get(program['adventure_name'], program['adventure_name'])
                    customized_level = class_adventures_formatted.get(str(program['level']))
                    if name in customized_level:
                        student_adventure_id = f"{student}-{program['adventure_name']}-{level}"
                        current_adventure = self.db.student_adventure_by_id(student_adventure_id)
                        if not current_adventure:
                            # store the adventure in case it's not in the table
                            current_adventure = self.db.store_student_adventure(
                                dict(id=f"{student_adventure_id}", ticked=False, program_id=program['id']))

                        current_program = dict(id=program['id'], level=str(program['level']),
                                               name=name, ticked=current_adventure['ticked'])

                        student_adventures[student_adventure_id] = program['id']
                        ticked_adventures[student].append(current_program)

        return students, class_, class_adventures_formatted, ticked_adventures, adventure_names, student_adventures


def add(username, action):
    """
    Adds aggregated stats for all users and fine-grained stats for logged-in users.
    Ensures logging stats will not cause a failure.
    """
    try:
        all_id = UserType.ANONYMOUS
        if username:
            action(username)
            # g.db instead of self.db since this function is not on a class
            is_student = g.db.get_student_classes_ids(username) != []
            all_id = UserType.STUDENT if is_student else UserType.LOGGED
        action(all_id.value)
    except Exception as ex:
        # adding stats should never cause failure. Log and continue.
        querylog.log_value(server_error=ex)


def _to_response_per_level(data):
    data.sort(key=lambda el: el["level"])
    return [{"level": f"L{entry['level']}", "data": _data_to_response_per_level(entry["data"])} for entry in data]


def _data_to_response_per_level(data):
    res = {}

    _add_value_to_result(res, "successful_runs", data["successful_runs"], is_counter=True)
    _add_value_to_result(res, "failed_runs", data["failed_runs"], is_counter=True)
    res["error_rate"] = _calc_error_rate(data.get("failed_runs"), data.get("successful_runs"))
    _add_exception_data(res, data)

    _add_value_to_result(res, "anonymous_runs", data["anonymous_runs"], is_counter=True)
    _add_value_to_result(res, "logged_runs", data["logged_runs"], is_counter=True)
    _add_value_to_result(res, "student_runs", data["student_runs"], is_counter=True)
    _add_value_to_result(res, "user_type_unknown_runs", data["user_type_unknown_runs"], is_counter=True)

    _add_value_to_result(res, "abandoned_quizzes", data["total_attempts"] - data["completed_attempts"], is_counter=True)
    _add_value_to_result(res, "completed_quizzes", data["completed_attempts"], is_counter=True)

    min_, max_, avg_ = _score_metrics(data["scores"])
    _add_value_to_result(res, "quiz_score_min", min_)
    _add_value_to_result(res, "quiz_score_max", max_)
    _add_value_to_result(res, "quiz_score_avg", avg_)

    return res


def _to_response(data, values_field, series_selector, values_map=None):
    """
    Transforms aggregated data to a response convenient for charts to use
        - values_field is what shows on the X-axis, e.g. level or week number
        - series_selector determines the data series, e.g. successful runs per level or occurrences of exceptions
    """

    res = {}
    for e in data:
        values = e[values_field]
        series = series_selector(e)
        if values not in res.keys():
            res[values] = {}

        d = e["data"]
        _add_dict_to_result(res[values], "successful_runs", series, d["successful_runs"], is_counter=True)
        _add_dict_to_result(res[values], "failed_runs", series, d["failed_runs"], is_counter=True)
        _add_dict_to_result(
            res[values], "abandoned_quizzes", series, d["total_attempts"] - d["completed_attempts"], is_counter=True
        )
        _add_dict_to_result(res[values], "completed_quizzes", series, d["completed_attempts"], is_counter=True)

        _add_value_to_result(res[values], "anonymous_runs", d["anonymous_runs"], is_counter=True)
        _add_value_to_result(res[values], "logged_runs", d["logged_runs"], is_counter=True)
        _add_value_to_result(res[values], "student_runs", d["student_runs"], is_counter=True)
        _add_value_to_result(res[values], "user_type_unknown_runs", d["user_type_unknown_runs"], is_counter=True)

        min_, max_, avg_ = _score_metrics(d["scores"])
        _add_dict_to_result(res[values], "quiz_score_min", series, min_)
        _add_dict_to_result(res[values], "quiz_score_max", series, max_)
        _add_dict_to_result(res[values], "quiz_score_avg", series, avg_)

        _add_exception_data(res[values], d)

    result = [{values_field: k, "data": _add_error_rate_from_dicts(v)} for k, v in res.items()]
    result.sort(key=lambda el: el[values_field])

    return [values_map(e) for e in result] if values_map else result


def _add_value_to_result(target, key, source, is_counter=False):
    if source is not None and (source > 0 if is_counter else True):
        if not target.get(key):
            target[key] = source
        else:
            target[key] += source


def _add_dict_to_result(target, key, series, source, is_counter=False):
    if source is not None and (source > 0 if is_counter else True):
        if not target.get(key):
            target[key] = {}
        target[key][series] = source


def _score_metrics(scores):
    if not scores:
        return None, None, None
    min_result = scores[0]
    max_result = scores[0]
    total = 0
    for s in scores:
        if s < min_result:
            min_result = s
        if s > max_result:
            max_result = s
        total += s
    return min_result, max_result, total / len(scores)


def _aggregate_for_keys(data, keys):
    """
    Aggregates data by one or multiple keys/dimensions. The implementation 'serializes' the
    values of supplied keys and later 'deserializes' the original values. Improve on demand.
    """

    result = {}
    for record in data:
        key = _aggregate_key(record, keys)
        result[key] = _add_program_run_data(result.get(key), record)
        result[key] = _add_quiz_data(result.get(key), record)
    return [_split_keys_data(k, v, keys) for k, v in result.items()]


def _aggregate_key(record, keys):
    return "#".join([str(record[key.name]) for key in keys])


def _initialize():
    return {
        "failed_runs": 0,
        "successful_runs": 0,
        "anonymous_runs": 0,
        "logged_runs": 0,
        "student_runs": 0,
        "user_type_unknown_runs": 0,
        "total_attempts": 0,
        "completed_attempts": 0,
        "scores": [],
    }


def _add_program_run_data(data, rec):
    if not data:
        data = _initialize()
    value = rec.get("successful_runs") or 0
    data["successful_runs"] += value

    _add_user_type_runs(data, rec.get("id"), value)
    _add_exception_data(data, rec, True)

    return data


def _add_quiz_data(data, rec):
    if not data:
        data = _initialize()
    data["total_attempts"] += rec.get("started") or 0
    data["completed_attempts"] += rec.get("finished") or 0
    data["scores"] += rec.get("scores") or []
    return data


def _add_exception_data(entry, data, include_failed_runs=False):
    exceptions = {k: v for k, v in data.items() if k.lower().endswith("exception")}
    for k, v in exceptions.items():
        if not entry.get(k):
            entry[k] = 0
        entry[k] += v
        if include_failed_runs:
            entry["failed_runs"] += v
            _add_user_type_runs(entry, entry.get("id"), v)


def _add_user_type_runs(data, id_, value):
    if id_ == UserType.ANONYMOUS.value:
        data["anonymous_runs"] += value
    if id_ == UserType.LOGGED.value:
        data["logged_runs"] += value
    if id_ == UserType.STUDENT.value:
        data["student_runs"] += value
    if id_ == UserType.ALL.value:
        data["user_type_unknown_runs"] += value


def _split_keys_data(k, v, keys):
    values = k.split("#")
    res = {keys[i].name: keys[i].class_(values[i]) for i in range(0, len(keys))}
    res["data"] = v
    return res


def _to_response_level_name(e):
    e["level"] = f"L{e['level']}"
    return e


def _add_error_rate_from_dicts(data):
    failed = data.get("failed_runs") or {}
    successful = data.get("successful_runs") or {}
    keys = set.union(set(failed.keys()), set(successful.keys()))
    data["error_rate"] = {k: _calc_error_rate(failed.get(k), successful.get(k)) for k in keys}
    return data


def _calc_error_rate(fail, success):
    failed = fail or 0
    successful = success or 0
    return (failed * 100) / max(1, failed + successful)


def get_general_class_stats(students):
    # g.db instead of self.db since this function is not on a class
    current_week = g.db.to_year_week(date.today())
    data = g.db.get_program_stats(students, None, None)
    successes = 0
    errors = 0
    weekly_successes = 0
    weekly_errors = 0

    for entry in data:
        entry_successes = int(entry.get("successful_runs", 0))
        entry_errors = sum([v for k, v in entry.items() if k.lower().endswith("exception")])
        successes += entry_successes
        errors += entry_errors
        if entry.get("week") == current_week:
            weekly_successes += entry_successes
            weekly_errors += entry_errors

    return {
        "week": {"runs": weekly_successes + weekly_errors, "fails": weekly_errors},
        "total": {"runs": successes + errors, "fails": errors},
    }
