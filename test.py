from project.fact_values import FactValue

serialised_fact_value = FactValue.serialize()
print(serialised_fact_value.deserialize().get_value())