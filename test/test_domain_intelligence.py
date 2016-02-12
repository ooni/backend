import shutil
import unittest

from pipeline.batch import domain_intelligence

class TestDownloadCitizenLabUrls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_lists_directory = domain_intelligence.download_citizen_lab_test_list()

    def test_get_hostname_category(self):
        assert len(domain_intelligence.get_url_category("http://www.google.com", self.test_lists_directory)) == 2

    def test_get_alexa_ranking(self):
        ranking = domain_intelligence.get_url_alexa_ranking("http://www.google.com")
        int(ranking)

    def test_get_number_of_google_results(self):
        results = domain_intelligence.get_number_of_google_results("http://www.torproject.org/")
        assert isinstance(results, int)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_lists_directory)

if __name__ == "__main__":
    unittest.main()
