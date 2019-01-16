# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from jinja2 import Environment, FileSystemLoader
from auto_nag import mail, utils
from auto_nag.people import People


class Nag(object):
    def __init__(self):
        super(Nag, self).__init__()
        self.people = People()
        self.send_nag_mail = True
        self.data = {}
        self.nag_date = None
        self.white_list = []
        self.black_list = []

    @staticmethod
    def get_from():
        return utils.get_config('auto_nag', 'from', 'release-mgmt@mozilla.com')

    @staticmethod
    def get_cc():
        return set(utils.get_config('auto_nag', 'cc', []))

    def get_priority(self, bug):
        tracking = bug[self.tracking]
        if tracking == 'blocking':
            return 'high'
        return 'normal'

    def filter_bug(self, priority):
        days = (utils.get_next_release_date() - self.nag_date).days
        weekday = self.nag_date.weekday()
        Mon = 0
        Thu = 2
        if priority == 'high':
            if days >= 20:
                return weekday == Thu
            if 5 <= days < 20:
                return weekday in {Mon, Thu}
            return True
        elif priority == 'normal':
            if days >= 15:
                return weekday == Thu
            if 3 <= days < 15:
                return weekday in {Mon, Thu}
            return True

        return weekday == Mon

    def get_people(self):
        return self.people

    def set_people_to_nag(self, bug):
        return bug

    def escalation(self, person, priority):
        days = (utils.get_next_release_date() - self.nag_date).days
        if priority == 'high':
            if days >= 20:
                return self.people.get_nth_manager_mail(person, 1)
            elif 15 <= days < 20:
                return self.people.get_nth_manager_mail(person, 2)
            elif 5 <= days < 15:
                return self.people.get_director_mail(person)
            else:
                return self.people.get_vp_mail(person)
        elif priority == 'normal':
            if days >= 15:
                return self.people.get_nth_manager_mail(person, 1)
            elif 10 <= days < 15:
                return self.people.get_nth_manager_mail(person, 2)
            elif 3 <= days < 10:
                return self.people.get_director_mail(person)
            else:
                return self.people.get_vp_mail(person)

        return self.people.get_nth_manager_mail(person, 1)

    def add(self, person, bug_data, priority='default'):
        if not self.people.is_mozilla(person):
            return False

        manager = self.escalation(person, priority)
        person = self.people.get_moz_mail(person)

        if manager in self.data:
            data = self.data[manager]
        else:
            self.data[manager] = data = {}
        if person in data:
            data[person].append(bug_data)
        else:
            data[person] = [bug_data]

        return True

    def nag_template(self):
        return ''

    def get_extra_for_nag_template(self):
        return {}

    def _is_in_list(self, mail, _list):
        for manager in _list:
            if self.people.is_under(mail, manager):
                return True
        return False

    def is_under(self, mail):
        if not self.white_list:
            if not self.black_list:
                return True
            return not self._is_in_list(mail, self.black_list)
        if not self.black_list:
            return self._is_in_list(mail, self.white_list)
        return self._is_in_list(mail, self.white_list) and not self._is_in_list(
            mail, self.black_list
        )

    def send_mails(self, title, dryrun=False):
        if not self.send_nag_mail:
            return

        env = Environment(loader=FileSystemLoader('templates'))
        common = env.get_template('common.html')
        login_info = utils.get_login_info()
        From = Nag.get_from()
        Default_Cc = Nag.get_cc()
        mails = self.prepare_mails()

        for m in mails:
            Cc = Default_Cc.copy()
            Cc.add(m['manager'])
            body = common.render(message=m['body'], query_url=None, has_table=True)
            mail.send(
                From,
                sorted(m['to']),
                title,
                body,
                Cc=sorted(Cc),
                html=True,
                login=login_info,
                dryrun=dryrun,
            )

    def prepare_mails(self):
        if not self.data:
            return []

        template = self.nag_template()
        if not template:
            return []

        extra = self.get_extra_for_nag_template()
        env = Environment(loader=FileSystemLoader('templates'))
        template = env.get_template(template)
        mails = []
        for manager, info in self.data.items():
            data = []
            To = sorted(info.keys())
            for person in To:
                bug_data = info[person]
                data += bug_data

            body = template.render(
                date=self.nag_date, extra=extra, plural=utils.plural, data=data
            )

            m = {'manager': manager, 'to': set(info.keys()), 'body': body}
            mails.append(m)

        return mails
