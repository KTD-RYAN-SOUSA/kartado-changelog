from math import sqrt
from statistics import stdev, variance

import geojson
from json_logic import add_operation

# json_logic customization
add_operation("sqrt", lambda num: sqrt(num))
add_operation("average", lambda *nums: sum(nums) / len(nums))
add_operation("standardDeviation", lambda *nums: stdev(nums))
add_operation("variance", lambda *nums: variance(nums))

geojson.geometry.DEFAULT_PRECISION = 15
