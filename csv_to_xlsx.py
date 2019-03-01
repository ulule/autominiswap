#!/usr/bin/python3
# encoding: utf-8

import argparse
import csv
import io
import sys
from xlsxwriter.workbook import Workbook

colors = [
    '#FFFFCC',
    '#AECF00',
    '#66FFFF',
    '#66FF99',
    '#00CCFF',
    '#CC99FF',
    '#FF99CC',
    '#DD4814',
    '#FFD320',
    '#99FF33',
    '#CCFFFF',
    '#99CCCC',
    '#9999FF',
    '#FF9999',
    '#993300',
    '#83CAFF',
    '#FFFF00',
    '#808080',
]


def get_color(value):
    try:
        value = int(value)
    except ValueError:
        return 'white'
    else:
        return colors[value % len(colors)]


def csv_to_xlsx(csv_input):
    output = io.BytesIO()
    workbook = Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet()
    center = workbook.add_format({'align': 'center'})

    reader = csv.reader(csv_input, delimiter=',')
    for r, row in enumerate(reader):
        for c, col in enumerate(row):
            if c == len(row) - 1:
                cell_format = workbook.add_format({'bg_color': get_color(col), 'align': 'center'})
                worksheet.write(r, c, col, cell_format)
            elif c == 0:
                worksheet.write(r, c, col)
            else:
                worksheet.write(r, c, col, center)

    worksheet.set_column(0, 0, 30)
    worksheet.set_column(1, 1, 40)
    worksheet.set_column(2, 2, 30)
    worksheet.set_column(3, 3, 15)
    workbook.close()

    return output


parser = argparse.ArgumentParser(description='Converts CSV swap results to XSLX.')
parser.add_argument('--input', required=False, default=None, help='Path to csv file')
parser.add_argument('--output', required=False, default=None, help='Path to xlsx file')


if __name__ == '__main__':
    args = parser.parse_args()
    if args.input:
        with open(args.input) as csv_file:
            result = csv_to_xlsx(csv_file)
    else:
        result = csv_to_xlsx(sys.stdin)

    result.seek(0)
    if args.output:
        with open(args.output, 'wb') as xlsx_file:
            xlsx_file.write(result.read())
    else:
        sys.stdout.buffer.write(result.read())
