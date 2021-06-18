#!/usr/bin/python3
# encoding: utf-8

import getopt
import functools
import sys
from collections import defaultdict
from math import ceil
import random
import csv
import os

choice = random.SystemRandom().choice
sample = random.SystemRandom().sample

SWAP_EXCLUSION = [name.lower() for name in os.getenv('SWAP_EXCLUSION', "").split(',')]


def get_data(delimiter=','):
    reader = csv.reader(sys.stdin, delimiter=delimiter)
    rows = [row for row in reader if row]
    return [(person, dpt, int(vacation)) for person, dpt, branch, vacation in rows[1:]]


def select_swap_people(people):
    people_by_dpt = defaultdict(list)
    for person, dpt, vacation in people:
        if person.lower() not in SWAP_LUNCH_EXCLUSION and vacation < SWAP_LUNCH_VACATION_LIMIT:
            people_by_dpt[dpt].append(person)

    return people_by_dpt


def redistribute_last_participants(last_participants, groups):
    if not groups:
        return [last_participants]

    for n, person in enumerate([person for person in last_participants]):
        groups[n % len(groups)].append(person)

    return groups


def sort_dpt_by_size(people_by_dpt, current_sort=None):
    if not current_sort:
        return sorted(people_by_dpt.keys(), key=lambda x: len(people_by_dpt[x]), reverse=True)

    def compare_dpt_size(dpt_a, dpt_b):
        dpt_a_size = people_by_dpt[dpt_a]
        dpt_b_size = people_by_dpt[dpt_b]

        if dpt_a_size < dpt_b_size:
            return -1
        elif dpt_a_size > dpt_b_size:
            return 1
        else:
            if not current_sort:
                return 0
            idx_dpt_a = current_sort.index(dpt_a)
            idx_dpt_b = current_sort.index(dpt_b)
            return 1 if idx_dpt_a < idx_dpt_b else -1

    return sorted(people_by_dpt.keys(), key=functools.cmp_to_key(compare_dpt_size), reverse=True)


def group_by(people_by_dpt, group_size):
    result = []
    sorted_dpt = None
    while people_by_dpt:
        sorted_dpt = sort_dpt_by_size(people_by_dpt, sorted_dpt)
        if len(sorted_dpt) == 1:
            return redistribute_last_participants(people_by_dpt[sorted_dpt[0]], result)
        group = []
        for i in range(group_size):
            try:
                selected_dpt = sorted_dpt[i]
            except IndexError:
                try:
                    selected_dpt = sorted_dpt[-1]
                except IndexError:
                    # If we still have an Index error at this point,
                    # it means we have an unfinished group and no more available participants.
                    # We will redistribute the member(s) of this last group onto other groups and return.
                    return redistribute_last_participants(group, result)

            selected = choice(people_by_dpt[selected_dpt])
            group.append(selected)

            people_by_dpt[selected_dpt].remove(selected)
            if not len(people_by_dpt[selected_dpt]):
                sorted_dpt.remove(selected_dpt)
                del people_by_dpt[selected_dpt]

        result.append(group)
    return result

def swap(people, group_size):
    people_by_dpt = select_swap_people(people)
    groups = group_by(people_by_dpt, group_size)

    result = {}
    for i, group in enumerate(groups):
        for person in group:
            result[person] = i + 1

    return result


def output_to_csv(people, by_swap, delimiter=',', output=sys.stdout):
    people_with_swap_groups = {}
    writer = csv.writer(output, delimiter=delimiter, quotechar='|', quoting=csv.QUOTE_MINIMAL)

    writer.writerow(('Nom', 'Coffee-mates', 'Département'))
    for person, dpt, _ in sorted(people, key=lambda x: x[0]):
        swapping_person = by_swap.get(person, '')
        if swapping_person:
            people_with_swap_groups[person] = [swapping_person, dpt]
            sorted_people_list = dict(sorted(people_with_swap_groups.items(), key=lambda item: item[1][0]))

    for person, metadata in sorted_people_list.items():
        writer.writerow((person, metadata[0], metadata[1]))


HELP = 'swap.py -s <swap_group_size>'

if __name__ == '__main__':
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hs:", ["swap-group=", "lunch-group=")
    except getopt.GetoptError:
        print(HELP)
        sys.exit(2)

    opts = dict(opts)

    if '-h' in opts:
        print(HELP)
        sys.exit(0)

    swap_group_size = opts.get('-s', opts.get('--swap-group', 3))

    data = get_data()
    swaps = swap(data, swap_group_size)

    output_to_csv(data, swaps)
