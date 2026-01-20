from . import Assessment

class Assessments:
    __assessments_dict: dict[str, Assessment] = dict()

    def get_assessments_dict(self):
        return self.__assessments_dict
    
    def set_assessments_list(self, assessments_dict: dict):
        self.__assessments_dict = assessments_dict

    def add_assessment(self, assessment: Assessment):
        self.__assessments_dict[assessment.get_assessment_name()]=assessment

    def get_assessment(self, assessment_name) -> Assessment:
        return self.__assessments_dict.get(assessment_name)