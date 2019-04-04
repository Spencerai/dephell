# built-in
from argparse import ArgumentParser
from collections import defaultdict
from datetime import date, timedelta
from itertools import zip_longest
from typing import Iterable, Iterator

import attr
import requests

# app
from ..config import builders
from .base import BaseCommand


@attr.s()
class DateList:
    start = attr.ib()
    end = attr.ib()
    _data = attr.ib(factory=dict, repr=False)

    def add(self, date: str, value: int):
        self._data[date] = value

    def __iter__(self) -> Iterator[int]:
        moment = self.start
        while moment <= self.end:
            yield self._data.get(str(moment), 0)
            moment += timedelta(1)


class PackageDownloadsCommand(BaseCommand):
    """Show downloads statistic for package from PyPI.org.

    https://dephell.readthedocs.io/en/latest/cmd-package-downloads.html
    """

    recent_url = 'https://pypistats.org/api/packages/{}/recent'
    categories = dict(
        pythons='https://pypistats.org/api/packages/{}/python_minor',
        systems='https://pypistats.org/api/packages/{}/system',
    )
    ticks = '_▁▂▃▄▅▆▇█'

    @classmethod
    def get_parser(cls):
        parser = ArgumentParser(
            prog='dephell package downloads',
            description=cls.__doc__,
        )
        builders.build_config(parser)
        builders.build_output(parser)
        builders.build_api(parser)
        builders.build_other(parser)
        parser.add_argument('name', help='package name')
        return parser

    def __call__(self):
        name = self.args.name.lower().replace('_', '-')
        data = dict()

        url = self.recent_url.format(name)
        response = requests.get(url)
        if response.status_code != 200:
            self.logger.error('invalid status code', extra=dict(
                code=response.status_code,
                url=url,
            ))
            return False
        body = response.json()['data']
        data['total'] = dict(
            day=body['last_day'],
            week=body['last_week'],
            month=body['last_month'],
        )

        for category_name, category_url in self.categories.items():
            url = category_url.format(name)
            response = requests.get(url)
            if response.status_code != 200:
                self.logger.error('invalid status code', extra=dict(
                    code=response.status_code,
                    url=url,
                ))
                return False
            body = response.json()['data']

            yesterday = date.today() - timedelta(1)
            grouped = defaultdict(lambda: DateList(start=yesterday - timedelta(30), end=yesterday))
            for line in body:
                category = line['category'].replace('.', '')
                grouped[category].add(date=line['date'], value=line['downloads'])

            data[category_name] = []
            for category, downloads in grouped.items():
                downloads = list(downloads)
                if sum(downloads) == 0:
                    continue
                data[category_name].append(dict(
                    category=category,
                    day=downloads[-1],
                    week=sum(downloads[-7:]),
                    month=sum(downloads),
                    chart=self.make_chart(downloads[-28:], group=7),
                ))

        print(self.get_value(data=data, key=self.config.get('filter')))
        return True

    def make_chart(self, values: Iterable[int], group: int = None) -> str:
        peek = max(values)
        if peek == 0:
            chart = self.ticks[-1] * len(values)
        else:
            chart = ''
            for value in values:
                index = round((len(self.ticks) - 1) * value / peek)
                chart += self.ticks[int(index)]
        if group:
            chunks = map(''.join, zip_longest(*[iter(chart)] * group, fillvalue=' '))
            chart = ' '.join(chunks).strip()
        return chart