import { useState } from "react";
import { Box, TextField, Button } from "@mui/material";
import axios from "axios";

const endpointMapping = {
  Notion: "notion",
  Airtable: "airtable",
  Hubspot: "hubspot",
};

export const DataForm = ({ integrationType, credentials }) => {
  const [loadedData, setLoadedData] = useState(null);
  const endpoint = endpointMapping[integrationType];

  const parseResponseData = (data) => {
    if (!data?.integration || !Array.isArray(data.integration))
      return "No data loaded.";
    return data.integration
      .map((item, idx) => {
        return `${idx + 1}. ${item.name} (Type: ${item.type}, ID: ${item.id})`;
      })
      .join("\n");
  };

  const handleLoad = async () => {
    try {
      const formData = new FormData();
      formData.append("credentials", JSON.stringify(credentials));
      const response = await axios.post(
        `http://localhost:8000/integrations/${endpoint}/load`,
        formData
      );
      const data = response.data;
      const parsed = parseResponseData(data);
      setLoadedData(parsed);
    } catch (e) {
      alert(e?.response?.data?.detail);
    }
  };

  return (
    <Box
      display="flex"
      justifyContent="center"
      alignItems="center"
      flexDirection="column"
      width="100%"
    >
      <Box display="flex" flexDirection="column" width="100%">
        <TextField
          label="Loaded Data"
          value={loadedData || ""}
          sx={{ mt: 2, width: "100%" }}
          multiline
          minRows={5}
          maxRows={10}
          InputLabelProps={{ shrink: true }}
          disabled
        />
        <Button onClick={handleLoad} sx={{ mt: 2 }} variant="contained">
          Load Data
        </Button>
        <Button
          onClick={() => setLoadedData(null)}
          sx={{ mt: 1 }}
          variant="contained"
        >
          Clear Data
        </Button>
      </Box>
    </Box>
  );
};
