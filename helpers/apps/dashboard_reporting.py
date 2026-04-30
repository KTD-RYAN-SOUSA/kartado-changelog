from collections import defaultdict

from rest_framework.response import Response

from apps.roads.models import Road


def float_range(start, end, inc):
    digits = len(str(inc).split(".")[1])
    result = []
    while 1:
        next_value = start + len(result) * inc
        if inc >= 0 and next_value >= end:
            result.append(round(next_value, digits))
            break
        elif inc <= 0 and next_value <= end:
            result.append(round(next_value, digits))
            break
        result.append(round(next_value, digits))

    return result


def int_range(start, stop, step):
    stop += step
    return list(range(start, stop, step))


def kms_range(start, stop, step):
    initial_round = (start // step) * step

    final_round_base = (stop // step) * step
    final_round = final_round_base + step

    if isinstance(step, float):
        range_list = float_range(initial_round, final_round, step)
    else:
        range_list = int_range(initial_round, final_round, step)

    return range_list


def get_count_by_date_field(list_value, steps):

    counts = dict()
    for i in list_value:
        counts[i] = counts.get(i, 0) + 1

    list_final = []
    for item in range(len(steps) - 1):
        val = 0
        initial = steps[item].date()
        final = steps[item + 1].date()

        for key, value in counts.items():
            if key:
                if (key >= initial) and (key < final):
                    val += value
        list_final.append(val)

    return list_final


def get_count_rain(rain_days, steps):

    list_final = []
    for item in range(len(steps) - 1):
        val = 0
        initial = steps[item].date()
        final = steps[item + 1].date()
        for key, value in rain_days.items():
            if (key >= initial) and (key < final):
                val += value
        list_final.append(val)

    return list_final


class ReportingCount:
    def __init__(
        self,
        period,
        steps,
        reportings,
        occ_types,
        reference_date,
        steps_rain,
        reportings_rain,
    ):
        self.period = period
        self.steps = steps
        self.reportings = reportings
        self.occ_types = occ_types
        self.field = reference_date + "__date"
        self.steps_rain = steps_rain
        self.rep_rain = reportings_rain

    def get_rain_by_day(self):

        counts = dict()
        for i, k in list(
            self.rep_rain.values_list("found_at__date", "form_data__rain")
        ):
            counts[i] = counts.get(i, 0)
            if k:
                counts[i] += k

        rain_reportings = []
        for item in range(len(self.steps_rain) - 1):
            val = 0
            initial_date = self.steps_rain[item].date()
            final_date = self.steps_rain[item + 1].date()
            for key, value in counts.items():
                if (key >= initial_date) and (key < final_date):
                    val += value
            rain_reportings.append(val)

        attributes = {
            self.steps_rain[item].date(): rain_reportings[item]
            for item in range(len(self.steps_rain) - 1)
        }

        return attributes

    def get_reportings(self):

        total = [
            get_count_by_date_field(
                list(
                    self.reportings.filter(occurrence_type=occ_type).values_list(
                        self.field, flat=True
                    )
                ),
                self.steps,
            )
            for occ_type in self.occ_types
        ]

        rain_by_day = self.get_rain_by_day()
        rains = get_count_rain(rain_by_day, self.steps)

        attributes = {
            "period": self.period,
            "reportings": [
                {
                    "start_date": self.steps[item].format(),
                    "end_date": self.steps[item + 1].format(),
                    "rain": rains[item],
                    "types": [
                        {"id": self.occ_types[i].pk, "count": total[i][item]}
                        for i in range(len(self.occ_types))
                    ],
                }
                for item in range(len(self.steps) - 1)
            ],
        }

        return attributes

    def get_response(self):

        return Response({"type": "ReportingCount", "attributes": self.get_reportings()})


class ReportingCountRoad:
    def __init__(self, km_step, road_name, reportings, occ_types, company):
        self.km_step = km_step
        self.roads = Road.objects.filter(name=road_name, company__pk=company)
        self.reportings = reportings.filter(road__in=self.roads)
        self.occ_types = occ_types

    def get_count(self, occ_type):
        kms = list(
            self.reportings.filter(occurrence_type=occ_type).values_list(
                "km", "end_km", "uuid"
            )
        )
        kms_and_uuids = defaultdict(list)
        #   Puts the reportings in kms_and_uuids taking the km and end_km into
        # account. kms_and_uuids uses the km_step in quilometers as keys for the
        # dict.
        for km, end_km, reporting_id in kms:
            km_start_step = int(km * 1000 / self.km_step)
            km_end_step = (
                int(end_km * 1000 / self.km_step)
                if end_km is not None
                else int(km * 1000 / self.km_step)
            )

            for road_km in range(
                min(km_start_step, km_end_step),
                max(km_start_step, km_end_step) + 1,
                1,
            ):
                kms_and_uuids[road_km * self.km_step / 1000].append(str(reporting_id))
        return kms_and_uuids

    def get_kms(self):

        all_marks = [
            item
            for dicts in self.roads.values_list("marks", flat=True)
            for item in dicts.values()
        ]
        kms = sorted(all_marks, key=lambda k: k["km"])
        initial = kms[0]["km"]
        final = kms[-1]["km"]
        steps = self.km_step / 1000

        return kms_range(initial, final, steps)

    def get_reportings(self):

        kms_list = self.get_kms()

        total = [
            {"occ_type": str(occ_type.pk), "count": self.get_count(occ_type)}
            for occ_type in self.occ_types
        ]

        attributes = [
            {
                "initial_km": kms_list[i],
                "final_km": kms_list[i + 1],
                "types": [
                    {
                        "id": item["occ_type"],
                        "count": len(item["count"].get(kms_list[i], [])),
                        "reportings": list(set(item["count"].get(kms_list[i], []))),
                    }
                    for item in total
                ],
            }
            for i in range(len(kms_list) - 1)
        ]

        return attributes

    def get_response(self):

        return Response(
            {"type": "ReportingCountRoad", "attributes": self.get_reportings()}
        )


class RainData:
    def __init__(self, steps, reportings):
        self.steps = steps
        self.reportings = reportings

    def get_reportings(self):

        counts = dict()
        for i, k in list(
            self.reportings.values_list("found_at__date", "form_data__rain")
        ):
            counts[i] = counts.get(i, 0)
            if k:
                counts[i] += k

        rain_reportings = []
        for item in range(len(self.steps) - 1):
            val = 0
            initial_date = self.steps[item].date()
            final_date = self.steps[item + 1].date()
            for key, value in counts.items():
                if (key >= initial_date) and (key < final_date):
                    val += value
            rain_reportings.append(val)

        attributes = [
            {"day": self.steps[item].date(), "rain": rain_reportings[item]}
            for item in range(len(self.steps) - 1)
        ]

        return attributes

    def get_response(self):

        return Response({"type": "RainData", "attributes": self.get_reportings()})
