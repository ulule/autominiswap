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

SWAP_EXCLUSION = [name.lower() for name in os.getenv('SWAP_EXCLUSION').split(',')]
SWAP_LUNCH_EXCLUSION = [name.lower() for name in os.getenv('SWAP_LUNCH_EXCLUSION').split(',')]
SWAP_VACATION_LIMIT = 4
SWAP_LUNCH_VACATION_LIMIT = 4


def get_data(delimiter=','):
    reader = csv.reader(sys.stdin, delimiter=delimiter)
    rows = [row for row in reader if row]
    return [(person, dpt, int(vacation)) for person, dpt, branch, vacation in rows[1:]]


def select_swap_people(people):
    people_by_dpt = defaultdict(list)
    for person, dpt, vacation in people:
        if person.lower() not in SWAP_EXCLUSION and vacation < SWAP_VACATION_LIMIT:
            people_by_dpt[dpt].append(person)

    return {dpt: sample(persons, int(ceil(len(persons)/2))) for dpt, persons in people_by_dpt.items()}


def select_swap_lunch_people(people):
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
    for group in groups:
        for i, person in enumerate(group):
            try:
                result[person] = group[i+1]
            except IndexError:
                result[person] = group[0]
    return result


def swap_lunch(people, group_size):
    people_by_dpt = select_swap_lunch_people(people)
    groups = group_by(people_by_dpt, group_size)

    result = {}
    for i, group in enumerate(groups):
        for person in group:
            result[person] = i + 1

    return result


def output_to_csv(people, by_swap, by_swap_lunch, delimiter=',', output=sys.stdout):
    writer = csv.writer(output, delimiter=delimiter, quotechar='|', quoting=csv.QUOTE_MINIMAL)

    writer.writerow(('Nom', 'Dpt', 'Va à la place de', 'Swap-lunch team'))
    for person, dpt, _ in sorted(people, key=lambda x: x[0]):
        person_swap = by_swap.get(person, '')
        person_swap_lunch = by_swap_lunch.get(person, '')
        if person_swap or person_swap_lunch:
            writer.writerow((person, dpt, person_swap, person_swap_lunch))


HELP = 'swap.py -s <swap_group_size> -l <swap_lunch_group_size> -d <csv_delimiter> -o <output_file>'

if __name__ == '__main__':
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hs:l:d:o:", ["swap-group=", "lunch-group=", "delimiter=", "ofile="])
    except getopt.GetoptError:
        print(HELP)
        sys.exit(2)

    opts = dict(opts)

    if '-h' in opts:
        print(HELP)
        sys.exit(0)

    swap_group_size = opts.get('-s', opts.get('--swap-group', 3))
    swap_lunch_group_size = opts.get('-l', opts.get('--lunch-group', 3))
    csv_delimiter = opts.get('-d', opts.get('--delimiter', ','))
    output_file = opts.get('-o', opts.get('--ofile', None))

    data = get_data(delimiter=csv_delimiter)
    swaps = swap(data, swap_group_size)
    swap_lunches = swap_lunch(data, swap_lunch_group_size)

    if output_file:
        with open(output_file, 'w') as csv_file:
            output_to_csv(data, swaps, swap_lunches, delimiter=csv_delimiter, output=csv_file)
    else:
        output_to_csv(data, swaps, swap_lunches, delimiter=csv_delimiter, output=sys.stdout)
