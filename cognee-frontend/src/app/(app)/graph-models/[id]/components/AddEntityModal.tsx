"use client";

import { useState } from "react";
import { Button, Flex, Modal, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { useTranslations } from "next-intl";

interface AddEntityModalProps {
  opened: boolean;
  onClose: () => void;
  onSubmit: (name: string, description?: string) => void;
}

const inputStyles = {
  label: { color: "#EDECEA" },
  description: { color: "rgba(237,236,234,0.45)" },
  input: {
    background: "rgba(255,255,255,0.06)",
    border: "1px solid rgba(255,255,255,0.12)",
    color: "#EDECEA",
  },
};

export default function AddEntityModal({ opened, onClose, onSubmit }: AddEntityModalProps) {
  const t = useTranslations("graphModels");
  const tCommon = useTranslations("common");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [nameError, setNameError] = useState("");

  function handleSubmit() {
    const trimmed = name.trim();
    if (!trimmed) {
      setNameError(t("addEntity.nameRequired"));
      return;
    }
    if (!/^[A-Z][a-zA-Z0-9]*$/.test(trimmed)) {
      setNameError(t("addEntity.pascalCase"));
      return;
    }
    onSubmit(trimmed, description.trim() || undefined);
    handleClose();
  }

  function handleClose() {
    setName("");
    setDescription("");
    setNameError("");
    onClose();
  }

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={t("addEntity.title")}
      centered
      radius="0.5rem"
      styles={{
        content: {
          background: "rgba(15,15,15,0.92)",
          backdropFilter: "blur(16px)",
          border: "1px solid rgba(255,255,255,0.1)",
        },
        header: { background: "transparent" },
        title: { color: "#EDECEA", fontWeight: 700 },
        close: { color: "rgba(237,236,234,0.5)" },
      }}
    >
      <Stack gap="0.75rem">
        <TextInput
          label={t("addEntity.name")}
          placeholder={t("addEntity.namePlaceholder")}
          description={t("addEntity.nameHint")}
          value={name}
          onChange={(e) => {
            setName(e.currentTarget.value);
            setNameError("");
          }}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
          error={nameError}
          styles={inputStyles}
          radius="0.5rem"
          autoFocus
        />
        <Textarea
          label={t("addEntity.description")}
          placeholder={t("addEntity.descriptionPlaceholder")}
          value={description}
          onChange={(e) => setDescription(e.currentTarget.value)}
          styles={inputStyles}
          radius="0.5rem"
          rows={2}
        />
        <Text size="xs" c="rgba(237,236,234,0.45)">
          {t("addEntity.tip")}
        </Text>
        <Flex justify="flex-end" gap="0.5rem" mt="0.25rem">
          <Button
            variant="default"
            onClick={handleClose}
            radius="0.5rem"
            styles={{ root: { background: "transparent", border: "1px solid rgba(255,255,255,0.15)", color: "rgba(237,236,234,0.8)" } }}
          >
            {tCommon("cancel")}
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!name.trim()}
            style={{ backgroundColor: "#6510F4" }}
            radius="0.5rem"
          >
            {t("addEntity.submit")}
          </Button>
        </Flex>
      </Stack>
    </Modal>
  );
}
